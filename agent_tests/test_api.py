import pytest
from fastapi.testclient import TestClient
from agentic.api import create_app
from agentic.engine import Agent
from test_engine import ScriptedModel, sequence

KEY = "unit-test-only-" + "a" * 32


def test_api_auth_and_validated_result(tmp_path, database):
    a = Agent(ScriptedModel(sequence()), database, tmp_path / "state.sqlite")
    with TestClient(create_app(a, KEY)) as c:
        assert c.get("/health").status_code == 401
        assert c.post("/agent/query", json={"question":"revenue"}).status_code == 401
        response = c.post("/agent/query", headers={"Authorization":"Bearer " + KEY},
                          json={"question":"Paid booked revenue?"})
        assert response.status_code == 200
        assert response.json()["result"]["rows"] == [[350]]
    a.close()


@pytest.mark.parametrize("payload", [{"question":""}, {"question":"x", "thread_id":"../other"},
                                     {"question":"x", "model_url":"http://attacker"}, {"question":"x"*2001}])
def test_api_input_restrictions(tmp_path, database, payload):
    a = Agent(ScriptedModel([]), database, tmp_path / "state.sqlite")
    with TestClient(create_app(a, KEY)) as c:
        assert c.post("/agent/query", json=payload, headers={"Authorization":"Bearer " + KEY}).status_code == 422
    a.close()


def test_refuses_short_api_key(tmp_path, database):
    a = Agent(ScriptedModel([]), database, tmp_path / "state.sqlite")
    with pytest.raises(ValueError):
        create_app(a, "short")
    a.close()


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_local_workbench_cors_preflight(tmp_path, database, origin):
    a = Agent(ScriptedModel([]), database, tmp_path / "state.sqlite")
    with TestClient(create_app(a, KEY)) as c:
        r = c.options("/agent/query", headers={"Origin":origin,"Access-Control-Request-Method":"POST",
                    "Access-Control-Request-Headers":"Authorization,Content-Type"})
        assert r.status_code == 200 and r.headers["Access-Control-Allow-Origin"] == origin
    a.close()
