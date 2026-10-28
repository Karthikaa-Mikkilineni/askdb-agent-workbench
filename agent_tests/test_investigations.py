"""Host-contract tests use scripted planners, not claimed LLM accuracy."""
import json
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from agentic.api import create_app
from agentic.investigations import (InvestigationWorkflow, InvestigationRequest,
    MetricCatalog, RequestConflict, TaskAudit, metric_sql)
from agentic.store import SQLiteAnalytics, seed


def plan(*metrics, group='all'):
    return json.dumps({'status':'ready','steps':[{'metric':m,'group_by':group,
                      'source_ids':['metric.'+m]} for m in metrics],'question':''})


class ScriptedPlanner:
    def __init__(self,*responses):self.responses=list(responses);self.calls=0
    def __call__(self,messages):
        self.calls+=1
        response=self.responses[min(self.calls-1,len(self.responses)-1)]
        if isinstance(response,Exception):raise response
        return response


@pytest.fixture
def database(tmp_path):
    path=tmp_path/'commerce.sqlite';seed(path)
    return SQLiteAnalytics(path)


@pytest.fixture
def workflow(tmp_path,database):
    made=[]
    def create(*responses,db=None,folder=None):
        w=InvestigationWorkflow(ScriptedPlanner(*responses),db or database,folder or tmp_path/str(len(made)))
        made.append(w);return w
    yield create
    for w in made:w.close()


def request(**kw):
    return {'request_id':'analysis-0001','question':'Compare paid booked and net revenue after refunds',**kw}


def test_multi_step_evidence_pack(workflow):
    w=workflow(plan('booked_revenue','net_revenue','refunds'))
    result=w.run(request(required_metrics=['booked_revenue','net_revenue','refunds'],group_by='all'))
    assert result['status']=='completed' and not result['review_required']
    assert [r['rows'] for r in result['results']]==[[[350]],[[315]],[[35]]]
    assert [r['node'] for r in result['trace']]==['retrieve','scope','plan','execute','verify','report']
    assert 'metric.net_revenue' in result['report'] and '315' in result['report']
    assert all(len(r['evidence_hash'])==64 for r in result['results'])


@pytest.mark.parametrize('metric,total',[('all_orders',4),('paid_orders',3),
    ('booked_revenue',350),('net_revenue',315),('refunds',35)])
@pytest.mark.parametrize('group',['all','region'])
def test_catalog_arithmetic_and_group_reconciliation(workflow,metric,total,group):
    w=workflow(plan(metric,group=group))
    result=w.run(request(required_metrics=[metric],group_by=group))
    assert result['status']=='completed'
    assert sum(row[-1] for row in result['results'][0]['rows'])==total


def test_fanout_counterexample(workflow,database):
    wrong=database.execute('SELECT SUM(o.total) AS value FROM orders o JOIN order_items i ON i.order_id=o.id WHERE o.status=\'paid\'')
    assert wrong['rows']==[[650]]
    result=workflow(plan('booked_revenue')).run(request(required_metrics=['booked_revenue'],group_by='all'))
    assert result['results'][0]['rows']==[[350]]


def test_wrong_metric_is_revised(workflow):
    w=workflow(plan('booked_revenue'),plan('net_revenue'))
    result=w.run(request(required_metrics=['net_revenue'],group_by='all'))
    assert result['status']=='completed' and result['model_calls']==2
    assert len(result['planning_errors'])==1


def test_persistent_wrong_contract_fails_without_queries(workflow):
    w=workflow(plan('booked_revenue'))
    result=w.run(request(required_metrics=['net_revenue']))
    assert result['status']=='failed' and result['results']==[]
    assert result['model_calls']==2


def test_fabricated_citation_fails(workflow):
    bad=plan('net_revenue').replace('metric.net_revenue','internet.approved')
    assert workflow(bad).run(request(required_metrics=['net_revenue']))['status']=='failed'


def test_unknown_tool_or_sql_is_not_accepted(workflow):
    bad='{"status":"ready","steps":[{"metric":"DROP TABLE orders","group_by":"all","source_ids":["metric.net_revenue"]}]}'
    assert workflow(bad).run(request())['status']=='failed'


def test_invalid_json_recovers_once(workflow):
    result=workflow('not-json',plan('net_revenue')).run(request(required_metrics=['net_revenue']))
    assert result['status']=='completed' and result['model_calls']==2


def test_provider_error_is_redacted(workflow):
    result=workflow(RuntimeError('credential=secret-value')).run(request())
    assert result['status']=='failed' and 'secret-value' not in json.dumps(result)


def test_clarification_does_not_execute(workflow):
    result=workflow('{"status":"clarify","steps":[],"question":"Booked or net revenue?"}').run(request(question='What is revenue?'))
    assert result['status']=='clarification_required' and result['results']==[]
    assert 'execute' not in [r['node'] for r in result['trace']]


def test_no_explicit_contract_requires_review(workflow):
    assert workflow(plan('net_revenue')).run(request())['review_required']


def test_idempotent_replay_survives_restart(workflow,tmp_path):
    folder=tmp_path/'durable'
    w=workflow(plan('net_revenue'),folder=folder)
    first=w.run(request(required_metrics=['net_revenue'],group_by='all'))
    other=workflow(RuntimeError('must not infer again'),folder=folder)
    second=other.run(request(required_metrics=['net_revenue'],group_by='all'))
    assert second['replayed'] and second['results']==first['results']
    assert other.planner.calls==0


def test_request_key_payload_conflict(workflow):
    w=workflow(plan('net_revenue'));w.run(request())
    with pytest.raises(RequestConflict):w.run(request(question='Different question'))


def test_running_claim_is_not_reexecuted(tmp_path):
    audit=TaskAudit(tmp_path/'audit.sqlite');req=InvestigationRequest(**request())
    assert audit.claim(req) is None
    with pytest.raises(RequestConflict):audit.claim(req)


class BrokenDatabase:
    def __init__(self,db,mode):self.db,self.mode,self.schema_calls=db,mode,0
    def schema(self):
        self.schema_calls+=1
        return {'changed':[]} if self.mode=='schema' and self.schema_calls>1 else self.db.schema()
    def execute(self,sql):
        if self.mode=='execution':raise RuntimeError('database secret detail')
        result=self.db.execute(sql)
        if 'GROUP BY' in sql:
            if self.mode=='total':result['rows'][0][-1]=999
            if self.mode=='duplicate':result['rows'].append(result['rows'][0])
            if self.mode=='shape':result['columns']=['bad','value']
            if self.mode=='nan':result['rows'][0][-1]=float('nan')
            if self.mode=='cap':result['rows']=[['region'+str(i),1] for i in range(50)]
        return result


@pytest.mark.parametrize('mode',['schema','execution','total','duplicate','shape','nan','cap'])
def test_bad_evidence_never_publishes_partial_results(workflow,database,mode):
    result=workflow(plan('net_revenue',group='region'),db=BrokenDatabase(database,mode)).run(
        request(required_metrics=['net_revenue'],group_by='region'))
    assert result['status']=='failed' and result['results']==[]
    assert 'secret detail' not in json.dumps(result)


def test_catalog_quotes_are_not_fts_injection():
    catalog=MetricCatalog()
    try:
        assert isinstance(catalog.retrieve('" OR net revenue; DROP TABLE cards --'),list)
        assert catalog.retrieve('net revenue')[0]['metric']=='net_revenue'
    finally:catalog.close()


def test_api_auth_replay_conflict_and_readback(workflow):
    w=workflow(plan('net_revenue'));key='x'*32
    with TestClient(create_app(object(),key,w)) as client:
        assert client.post('/analysis/tasks',json=request()).status_code==401
        headers={'Authorization':'Bearer '+key}
        first=client.post('/analysis/tasks',json=request(),headers=headers)
        assert first.status_code==200 and first.json()['status']=='completed'
        assert client.post('/analysis/tasks',json=request(),headers=headers).json()['replayed']
        assert client.get('/analysis/tasks/analysis-0001',headers=headers).json()['status']=='completed'
        assert client.post('/analysis/tasks',json=request(question='changed'),headers=headers).status_code==409
        assert client.get('/analysis/tasks/missing',headers=headers).status_code==404
        assert client.post('/analysis/tasks',json={**request(),'arbitrary_url':'http://example.org'},headers=headers).status_code==422


@pytest.mark.parametrize('changes',[{'question':' '},{'required_metrics':['net_revenue','net_revenue']},
    {'request_id':'../../etc/passwd'},{'required_metrics':['conversion']},{'group_by':'raw_sql'}])
def test_invalid_input_contract(changes):
    with pytest.raises(ValueError):InvestigationRequest.model_validate(request(**changes))


def test_template_rejects_unknown_metric_and_group():
    with pytest.raises(ValueError):metric_sql('shell','all')
    with pytest.raises(ValueError):metric_sql('net_revenue','country')


def test_report_escapes_untrusted_region_markup(workflow,database):
    import sqlite3
    with sqlite3.connect(database.path) as conn:
        conn.execute('UPDATE customers SET region=? WHERE id=1',('<script>alert(1)</script>',))
    result=workflow(plan('net_revenue',group='region')).run(request(required_metrics=['net_revenue'],group_by='region'))
    assert result['status']=='completed'
    assert '<script>' not in result['report'] and '&lt;script&gt;' in result['report']


def test_unsupported_conversion_stops_before_model(workflow):
    w=workflow(RuntimeError('must not be called'))
    r=w.run(request(question='What is visit-to-purchase conversion?'))
    assert r['status']=='clarification_required' and w.planner.calls==0
    assert r['model_calls']==0 and r['results']==[]


def test_ambiguous_revenue_uses_capability_policy(workflow):
    w=workflow(RuntimeError('must not be called'))
    r=w.run(request(question='Show our revenue by region'))
    assert r['status']=='clarification_required' and w.planner.calls==0


def test_comparison_is_not_mistaken_for_ambiguity(workflow):
    r=workflow(plan('booked_revenue','net_revenue')).run(request(step_budget=2))
    assert r['status']=='completed'


def test_plan_compiler_only_emits_valid_catalog_choices():
    from agentic.investigations import candidate_plans,AnalysisPlan,CARDS
    bundle={'request':request(step_budget=4),'retrieved_cards':[{'metric':m} for m in CARDS]}
    choices=candidate_plans(bundle)
    assert len(choices)==61
    for choice in choices:
        parsed=AnalysisPlan.model_validate_json(choice)
        for step in parsed.steps:assert step.source_ids==['metric.'+step.metric]


def test_plan_compiler_honors_explicit_contract():
    from agentic.investigations import candidate_plans,AnalysisPlan
    choices=candidate_plans({'request':request(required_metrics=['net_revenue'],group_by='region'),
                            'retrieved_cards':[{'metric':'net_revenue'}]})
    plans=[AnalysisPlan.model_validate_json(c) for c in choices]
    ready=[p for p in plans if p.status=='ready']
    assert len(ready)==1 and ready[0].steps[0].group_by=='region'


class CharTokenizer:
    eos_token_id=999
    def encode(self,text,add_special_tokens=False):return [ord(c) for c in text]

class Tokens:
    def __init__(self,ids):self.ids=ids
    def tolist(self):return self.ids


def test_token_trie_branches_only_to_allowed_output():
    from agentic.models import prefix_constraint
    f=prefix_constraint(CharTokenizer(),['{"a":1}','{"a":2}'],prompt_length=2)
    assert f(0,Tokens([9,9]))==[ord('{')]
    assert f(0,Tokens([9,9,*map(ord,'{"a":')]))==[ord('1'),ord('2')]
    assert f(0,Tokens([9,9,*map(ord,'{"a":1}')]))==[999]
    with pytest.raises(ValueError):f(0,Tokens([9,9,ord('x')]))


@pytest.mark.parametrize('choices',[[],['x']*65,['x'*501]])
def test_trie_rejects_unbounded_grammar(choices):
    from agentic.models import prefix_constraint
    with pytest.raises(ValueError):prefix_constraint(CharTokenizer(),choices,0)


def test_single_metric_budget_blocks_unrequested_expansion(workflow):
    r=workflow(plan('net_revenue','refunds')).run(request(question='Total paid net revenue after refunds?'))
    assert r['status']=='failed' and r['results']==[]


def test_default_grammar_only_allows_one_metric():
    from agentic.investigations import candidate_plans,AnalysisPlan,CARDS
    choices=candidate_plans({'request':request(),'retrieved_cards':[{'metric':m} for m in CARDS]})
    assert len(choices)==11
    assert all(len(AnalysisPlan.model_validate_json(c).steps)<=1 for c in choices)
