"""Small transparent capability probe, not a general agent benchmark."""
import argparse
import json
import sys
import tempfile
import time
import socket
import threading
import secrets
import httpx
import uvicorn
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))
from agentic.engine import Agent
from agentic.api import create_app
from agentic.models import LocalTransformersModel
from agentic.policy import validate
from agentic.store import METRICS, TABLES, SQLiteAnalytics, seed

CASES = [
    {"id":"order_count", "question":"How many orders are in the database, including cancelled orders?", "rows":[[4]]},
    {"id":"paid_count", "question":"How many orders have status paid?", "rows":[[3]]},
    {"id":"booked", "question":"What is total booked revenue from paid orders, before subtracting refunds?", "rows":[[350]]},
    {"id":"net", "question":"What is total net revenue from paid orders after subtracting all refunds?", "rows":[[315]]},
    {"id":"region_net", "question":"Show net revenue by customer region for paid orders, after all refunds. Avoid multiplying orders by their items.", "rows":[["East",135],["West",180]]},
    {"id":"ambiguous", "question":"What is our revenue?", "clarify": True},
]


def canonical(rows):
    def normalize(x):
        try:
            return str(Decimal(str(x)).normalize())
        except InvalidOperation:
            return str(x)
    return sorted([tuple(normalize(x) for x in row) for row in rows])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-name", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--cases", help="Optional comma-separated case IDs for targeted reproduction")
    parser.add_argument("--output", default="evidence/live-model-evaluation.json")
    args = parser.parse_args()
    model = LocalTransformersModel(args.model)
    reports = []
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        seed(folder / "demo.sqlite")
        database = SQLiteAnalytics(folder / "demo.sqlite")
        agent = Agent(model, database, folder / "state.sqlite")
        key = secrets.token_hex(24)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(agent, key), log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets":[sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            raise RuntimeError("API server failed to start")
        for case in CASES:
            if args.cases and case["id"] not in args.cases.split(","):
                continue
            start = time.perf_counter()
            response = httpx.post(f"http://127.0.0.1:{port}/agent/query", json={"question":case["question"]},
                                  headers={"Authorization":"Bearer " + key}, timeout=600, trust_env=False)
            response.raise_for_status()
            result = response.json()
            correct = (result["status"] == "needs_clarification") if case.get("clarify") else (
                result["status"] == "completed" and canonical(result["result"].get("rows", [])) == canonical(case["rows"]))
            reports.append({**case, "correct": correct, "seconds": round(time.perf_counter()-start,3), "agent": result})
            Path(args.output).write_text(json.dumps({"model":args.model_name, "mode":"real local CPU inference",
                "transport":"real localhost HTTP through FastAPI/Uvicorn", "data":"synthetic commerce", "cases":reports}, indent=2))
            print(case["id"], result["status"], correct, result["calls"], flush=True)
        server.should_exit = True
        thread.join(timeout=10)
        agent.close()
    print("Task success", sum(r["correct"] for r in reports), "/", len(reports), flush=True)


if __name__ == "__main__":
    main()
