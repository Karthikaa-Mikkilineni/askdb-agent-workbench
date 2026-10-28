"""Quality gates must reject plausible but wrong financial answers."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).parent))
from benchmark_inference import contexts, quality, seed, SQLiteAnalytics, resident_bytes

def test_kernel_self_rss_is_plausible():
    assert resident_bytes() > 1024**2

@pytest.fixture
def db(tmp_path):
    path=tmp_path/'fixture.sqlite'
    seed(path)
    return SQLiteAnalytics(path)

def test_exact_net_answer(db):
    case={'rows':[[315]]}
    text=json.dumps({'tool':'validate_sql','args':{'sql':"SELECT SUM(net_revenue) FROM order_financials WHERE status='paid'"}})
    assert quality(text,case,db)['correct']

def test_wrong_metric_is_not_success(db):
    text=json.dumps({'tool':'validate_sql','args':{'sql':"SELECT SUM(booked_revenue) FROM order_financials WHERE status='paid'"}})
    result=quality(text,{'rows':[[315]]},db)
    assert result['valid_action'] and not result['correct']

def test_extra_answer_column_fails_strict_rubric(db):
    text=json.dumps({'tool':'validate_sql','args':{'sql':'SELECT 315 AS net, 350 AS booked'}})
    assert not quality(text,{'rows':[[315]]},db)['correct']

def test_mutation_is_rejected(db):
    text=json.dumps({'tool':'validate_sql','args':{'sql':'DELETE FROM orders'}})
    result=quality(text,{'rows':[]},db)
    assert not result['correct'] and 'error' in result
    assert db.execute('SELECT COUNT(*) FROM orders')['rows']==[[4]]

def test_clarification_requires_question(db):
    assert quality('{"tool":"clarify","args":{"question":"Booked or net revenue?"}}',{'clarify':True},db)['correct']
    assert not quality('{"tool":"clarify","args":{"question":""}}',{'clarify':True},db)['correct']

def test_invalid_json_is_not_valid_action(db):
    assert not quality('not JSON',{'rows':[[4]]},db)['valid_action']

def test_contexts_have_fixed_tool_observations(db):
    cases=contexts(db)
    assert len(cases)==6
    for case in cases:
        assert len(case['messages'])==6
        assert 'UNTRUSTED TOOL OBSERVATION' in case['messages'][-1]['content']

def test_unknown_tool_is_not_valid_action(db):
    assert not quality('{"tool":"shell","args":{}}',{'rows':[]},db)['valid_action']

@pytest.mark.parametrize('threads',[0,9,True,'4'])
def test_provider_rejects_invalid_thread_budget(threads):
    from agentic.models import LocalTransformersModel
    with pytest.raises(ValueError,match='threads'):
        LocalTransformersModel('/not-loaded',threads=threads)

def test_provider_rejects_string_cache_flag():
    from agentic.models import LocalTransformersModel
    with pytest.raises(ValueError,match='boolean'):
        LocalTransformersModel('/not-loaded',use_cache='false')
