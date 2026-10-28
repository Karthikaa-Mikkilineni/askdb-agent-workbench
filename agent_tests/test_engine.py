import json
import uuid
import pytest
from agentic.engine import Agent


def action(tool, **args):
    return json.dumps({"tool": tool, "args": args})


class ScriptedModel:
    """CONTROLLED model double, never counted as LLM accuracy evidence."""
    def __init__(self, actions):
        self.actions = iter(actions)
    def __call__(self, messages):
        next_action = next(self.actions)
        if callable(next_action):
            return next_action(messages)
        return next_action


def token_action(tool):
    def make(messages):
        for message in reversed(messages):
            if message["content"].startswith("UNTRUSTED TOOL OBSERVATION: "):
                event = json.loads(message["content"].split(": ", 1)[1])
                if event["tool"] == "validate_sql" and event["ok"]:
                    return action(tool)
        raise AssertionError("No validation token")
    return make


def sequence(sql="SELECT SUM(total) AS booked FROM orders WHERE status='paid'"):
    return [action("inspect_schema"), action("metric_definitions"), action("validate_sql", sql=sql),
            token_action("explain_sql"), token_action("execute_sql"), action("finish")]


def run(tmp_path, database, actions, **kwargs):
    agent = Agent(ScriptedModel(actions), database, tmp_path / "state.sqlite", **kwargs)
    try:
        return agent.run("What is paid booked revenue?")
    finally:
        agent.close()


def test_tool_loop_returns_execution_evidence(tmp_path, database):
    result = run(tmp_path, database, sequence())
    assert result["status"] == "completed"
    assert result["result"]["rows"] == [[350]]
    assert len(result["trace"]) == 5
    assert len(result["result"]["evidence_hash"]) == 64


def test_cannot_finish_without_evidence(tmp_path, database):
    r = run(tmp_path, database, [action("finish")] * 3)
    assert r["status"] == "budget_exhausted" and r["errors"] == 3
    assert r["result"] == {}


def test_cannot_skip_validation(tmp_path, database):
    r = run(tmp_path, database, [action("execute_sql", token="forged")] * 3)
    assert all(not e["ok"] for e in r["trace"])


def test_cannot_skip_explain(tmp_path, database):
    r = run(tmp_path, database, [action("inspect_schema"),
        action("validate_sql", sql="SELECT id FROM orders"), token_action("execute_sql"),
        token_action("explain_sql"), token_action("execute_sql"), action("finish")])
    assert r["status"] == "completed" and r["errors"] == 1


def test_cannot_write_without_schema(tmp_path, database):
    r = run(tmp_path, database, [action("validate_sql", sql="SELECT id FROM orders")] * 3)
    assert r["errors"] == 3 and r["result"] == {}


def test_query_revision_invalidates_old_token(tmp_path, database):
    actions = sequence("SELECT id FROM orders")[:3]
    old = []
    def save_and_revise(messages):
        event = json.loads(messages[-1]["content"].split(": ", 1)[1])
        old.append(event["observation"]["token"])
        return action("validate_sql", sql="SELECT region FROM customers")
    actions += [save_and_revise, lambda _: action("execute_sql", token=old[0]),
                token_action("explain_sql"), token_action("execute_sql"), action("finish")]
    r = run(tmp_path, database, actions)
    assert r["errors"] == 1 and r["status"] == "completed"


def test_recovers_from_unknown_column(tmp_path, database):
    actions = sequence("SELECT SUM(nonexistent) FROM orders")[:4] + sequence()[2:]
    r = run(tmp_path, database, actions)
    assert r["status"] == "completed" and r["errors"] == 1
    assert r["result"]["rows"] == [[350]]


def test_blocks_mutation_then_recovers(tmp_path, database):
    r = run(tmp_path, database, [action("inspect_schema"),
        action("validate_sql", sql="DELETE FROM orders"), *sequence()[2:]])
    assert r["errors"] == 1 and r["result"]["rows"] == [[350]]


def test_invalid_json_is_budgeted(tmp_path, database):
    r = run(tmp_path, database, ["not JSON"] * 3)
    assert r["calls"] == 3 and r["status"] == "budget_exhausted"


@pytest.mark.parametrize("prefix", ["```json\n", "```\n"])
def test_entire_fenced_json_is_validated(tmp_path, database, prefix):
    r = run(tmp_path, database, [prefix + action("clarify", question="Booked or net?") + "\n```"])
    assert r["status"] == "needs_clarification" and r["errors"] == 0


def test_unknown_tool_rejected(tmp_path, database):
    r = run(tmp_path, database, [action("shell", command="ls")] * 3)
    assert r["status"] == "budget_exhausted"


def test_extra_tool_arguments_rejected(tmp_path, database):
    r = run(tmp_path, database, [action("inspect_schema", path="/etc/passwd")] * 3)
    assert all(not e["ok"] for e in r["trace"])


def test_bounded_loop_even_without_errors(tmp_path, database):
    r = run(tmp_path, database, [action("inspect_schema")] * 5, max_calls=5)
    assert r["calls"] == 5 and r["status"] == "budget_exhausted"


def test_provider_error_does_not_leak_secret(tmp_path, database):
    def crash(_):
        raise RuntimeError("secret-api-key-abc")
    r = run(tmp_path, database, [crash])
    assert r["status"] == "model_unavailable" and "secret-api-key" not in json.dumps(r)


def test_schema_drift_invalidates_query(tmp_path, database):
    original = database.schema
    n = [0]
    def drift():
        n[0] += 1
        schema = original()
        if n[0] > 1:
            schema["orders"].append({"name":"new_column", "type":"TEXT"})
        return schema
    database.schema = drift
    r = run(tmp_path, database, sequence()[:4] + [action("clarify", question="Schema changed; retry?")])
    assert r["errors"] == 1 and r["result"] == {}
    assert r["status"] == "needs_clarification"


def test_clarification_survives_process_recreation(tmp_path, database):
    checkpoint = tmp_path / "state.sqlite"
    a = Agent(ScriptedModel([action("clarify", question="Booked or net revenue?")]), database, checkpoint)
    first = a.run("Revenue?")
    a.close()
    def check_context(messages):
        assert any(m["content"] == "Revenue?" for m in messages)
        assert messages[-1]["content"] == "Booked, paid orders only"
        return action("inspect_schema")
    b = Agent(ScriptedModel([check_context, *sequence()[1:]]), database, checkpoint)
    second = b.run("Booked, paid orders only", first["thread_id"])
    b.close()
    assert second["status"] == "completed" and second["result"]["rows"] == [[350]]


def test_threads_do_not_share_history(tmp_path, database):
    def check_new(messages):
        assert not any(m["content"] == "private first question" for m in messages)
        return action("clarify", question="Define conversion?")
    a = Agent(ScriptedModel([action("clarify", question="First?"), check_new]), database, tmp_path / "state.sqlite")
    a.run("private first question")
    assert a.run("second question")["status"] == "needs_clarification"
    a.close()


def test_fanout_fixture_has_distinct_wrong_answer(database):
    wrong = database.execute("SELECT SUM(o.total) FROM orders o JOIN order_items i ON i.order_id=o.id WHERE o.status='paid'")
    assert wrong["rows"] == [[650]]  # Correct order-grain booked revenue is 350.


def test_matching_sql_reference_is_allowed(tmp_path, database):
    sql = "SELECT SUM(total) AS booked FROM orders WHERE status='paid'"
    steps = sequence(sql)[:3] + [action("explain_sql", sql=sql), action("execute_sql", sql=sql), action("finish")]
    r = run(tmp_path, database, steps)
    assert r["status"] == "completed" and r["result"]["rows"] == [[350]]


def test_sql_reference_cannot_change_after_validation(tmp_path, database):
    steps = sequence()[:4] + [action("execute_sql", sql="DELETE FROM orders"),
                             action("clarify", question="Which metric?")]
    r = run(tmp_path, database, steps)
    assert r["errors"] == 1 and r["result"] == {}


@pytest.mark.parametrize("question", ["", " " * 10, "x" * 2001])
def test_question_limits(tmp_path, database, question):
    a = Agent(ScriptedModel([]), database, tmp_path / "state.sqlite")
    with pytest.raises(ValueError):
        a.run(question)
    a.close()
