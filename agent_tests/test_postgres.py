"""Run explicitly with ASKDB_TEST_DSN; never silently treated as executed."""
import os
import pytest
from agentic.engine import Agent
from agentic.policy import validate
from agentic.store import PostgresAnalytics, TABLES
from test_engine import ScriptedModel, sequence

pytestmark = pytest.mark.skipif(not os.getenv("ASKDB_TEST_DSN"), reason="PostgreSQL DSN not configured")


@pytest.fixture
def pg():
    return PostgresAnalytics(os.environ["ASKDB_TEST_DSN"])


def test_postgres_schema(pg):
    assert set(pg.schema()) == TABLES


def test_postgres_investigation_workflow(tmp_path,pg):
    import json
    from agentic.investigations import InvestigationWorkflow
    def planner(messages):
        return json.dumps({'status':'ready','steps':[
            {'metric':m,'group_by':'region','source_ids':['metric.'+m]}
            for m in ['booked_revenue','net_revenue']], 'question':''})
    workflow=InvestigationWorkflow(planner,pg,tmp_path/'investigation')
    try:
        result=workflow.run({'request_id':'postgres-investigation','question':'Compare booked and net by region',
                             'required_metrics':['booked_revenue','net_revenue'],'group_by':'region'})
        assert result['status']=='completed'
        assert [[float(row[-1]) for row in r['rows']] for r in result['results']]==[[150,200],[135,180]]
        assert workflow.run({'request_id':'postgres-investigation','question':'Compare booked and net by region',
                             'required_metrics':['booked_revenue','net_revenue'],'group_by':'region'})['replayed']
    finally:workflow.close()


def test_postgres_explain_and_exact_revenue(pg):
    sql, _ = validate("SELECT SUM(total) FROM orders WHERE status='paid'", TABLES)
    assert pg.explain(sql)["total_cost"] >= 0
    assert float(pg.execute(sql)["rows"][0][0]) == 350


def test_postgres_read_only_transaction(pg):
    with pytest.raises(Exception) as exc:
        pg.execute("DELETE FROM orders")
    assert getattr(exc.value, "pgcode", None) in {"25006", "42501"}


def test_postgres_cost_budget(pg):
    pg.max_cost = 0
    with pytest.raises(ValueError, match="cost"):
        pg.explain("SELECT id FROM orders")


def test_postgres_complete_graph(tmp_path, pg):
    a = Agent(ScriptedModel(sequence()), pg, tmp_path / "state.sqlite")
    r = a.run("Paid booked revenue?")
    a.close()
    assert r["status"] == "completed" and float(r["result"]["rows"][0][0]) == 350


def test_postgres_unknown_column_recovery(tmp_path, pg):
    steps = sequence("SELECT nonexistent FROM orders")[:4] + sequence()[2:]
    a = Agent(ScriptedModel(steps), pg, tmp_path / "state.sqlite")
    r = a.run("Paid booked revenue?")
    a.close()
    if os.getenv("ASKDB_CAPTURE_TRACE"):
        import json
        from pathlib import Path
        Path(os.environ["ASKDB_CAPTURE_TRACE"]).write_text(json.dumps(r, indent=2))
    assert r["status"] == "completed" and r["errors"] == 1, r
    assert "42703" in r["trace"][3]["error"]


def test_postgres_child_preaggregation(pg):
    sql, _ = validate("WITH r AS (SELECT order_id,SUM(amount) AS refund FROM refunds GROUP BY order_id) "
                      "SELECT SUM(o.total-COALESCE(r.refund,0)) FROM orders o "
                      "LEFT JOIN r ON r.order_id=o.id WHERE o.status='paid'", TABLES)
    assert float(pg.execute(sql)["rows"][0][0]) == 315


def test_postgres_approved_metric_view(pg):
    sql, _ = validate("SELECT COUNT(*),SUM(booked_revenue),SUM(net_revenue) "
                      "FROM order_financials WHERE status='paid'", TABLES)
    assert [float(value) for value in pg.execute(sql)["rows"][0]] == [3,350,315]
