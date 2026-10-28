"""UI fixture using a SCRIPTED model; never reported as LLM evaluation."""
import json
import sys
import tempfile
from pathlib import Path
import uvicorn
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from agentic.api import create_app
from agentic.engine import Agent
from agentic.store import SQLiteAnalytics, seed

steps = [
 {"tool":"inspect_schema","args":{}},
 {"tool":"validate_sql","args":{"sql":"SELECT SUM(total) AS booked FROM orders WHERE status='paid'"}},
 {"tool":"explain_sql","args":{}},{"tool":"execute_sql","args":{}},
 {"tool":"clarify","args":{"question":"Booked or net revenue?"}},
 {"tool":"inspect_schema","args":{}},
 {"tool":"validate_sql","args":{"sql":"SELECT COUNT(*) AS paid_orders FROM orders WHERE status='paid'"}},
 {"tool":"explain_sql","args":{}},{"tool":"execute_sql","args":{}}
]
class ScriptedModel:
    def __call__(self, messages):
        return json.dumps(steps.pop(0))

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        folder=Path(folder)
        seed(folder / "data.sqlite")
        agent=Agent(ScriptedModel(), SQLiteAnalytics(folder / "data.sqlite"), folder / "state.sqlite")
        try:
            uvicorn.run(create_app(agent,"browser-fixture-only-"+"a"*32), host="127.0.0.1",port=8081,log_level="error")
        finally:
            agent.close()
