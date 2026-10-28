# AskDB: stateful SQL agent with evidence-backed results

This extends the existing Python/FastAPI and React AskDB project. The legacy
`/query` application is preserved. The new, separate `/agent/query` service uses
LangGraph, structured LLM actions, guarded SQL tools and SQLite checkpoints.

The distinctive test problem is **metric ambiguity and join fanout**: a
synthetic order can have several items and refunds. Valid SQL can overcount
revenue. An approved order_financials view defines revenue at one row per order.
The agent can consult metric definitions, inspect metadata, request
clarification and revise a query after errors. It returns database evidence,
not a model-invented numeric answer. See METRICS.md for measured results and
limitations; this is a local portfolio prototype.

## Quick start: hosted OpenAI-compatible model

Use Python 3.12 and a new virtual environment separate from the old backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/agent-requirements.txt
export ASKDB_API_KEY="$(python -c 'import secrets; print(secrets.token_hex(24))')"
export ASKDB_LLM_BASE_URL="https://YOUR_PROVIDER_BASE_URL/v1"
export ASKDB_LLM_MODEL="YOUR_MODEL_IDENTIFIER"
export ASKDB_LLM_API_KEY="YOUR_PROVIDER_KEY"
PYTHONPATH=backend uvicorn agentic.api:app_factory --factory --host 127.0.0.1 --port 8081
```

Supply your own explicit provider configuration. The hosted adapter is tested
with a mock HTTP transport; paid/provider-hosted inference is not claimed.
The local model route below was exercised with real inference.

In another terminal with ASKDB_API_KEY set to the same key:

```bash
curl http://127.0.0.1:8081/agent/query \
  -H "Authorization: Bearer $ASKDB_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is paid booked revenue before refunds?"}'
```

The default database is a small **synthetic** SQLite commerce fixture. For a
pending clarification, submit the answer with the returned `thread_id`.
Completed jobs start a new question context. Do not share this local endpoint
or put real customer data in the demo.

## Real local model, no provider key

```bash
pip install -r backend/agent-local-requirements.txt
python scripts/download-local-model.py
export ASKDB_LOCAL_MODEL="$PWD/.local-models/qwen3-1.7B"
export ASKDB_API_KEY="$(python -c 'import secrets; print(secrets.token_hex(24))')"
PYTHONPATH=backend uvicorn agentic.api:app_factory --factory --host 127.0.0.1 --port 8081
```

Download requires several GB of disk and network access. Model weights are
not bundled. A CPU-only torch installation may be preferable; the evidence
records the CPU build used here. Inference latency and model reliability
vary considerably with hardware, model and prompt.

## React workbench

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open the Vite URL, paste the local API key into the password field, and ask a
question. The key stays in component memory; it is not persisted to browser
storage. The workbench shows status, clarification, executed SQL, evidence
rows and each tool call. A switch preserves the original query interface,
which still expects its separate legacy backend on port 8000. Original
setup instructions are in docs/LEGACY_README.md and README_V2.md.

## Tests

```bash
PYTHONPATH=backend python -m pytest agent_tests backend/tests -q
cd frontend && npm run build
```

Nine PostgreSQL checks skip unless `ASKDB_TEST_DSN` is configured. For a
**dedicated empty test database**, `scripts/seed-postgres.py` seeds the fixture
using ASKDB_ADMIN_DSN and creates a SELECT-only test role. Never run it
against a populated application database. The GitHub workflow supplies an
example native PostgreSQL service configuration, not evidence of a remote run.

Optional restricted-environment verification uses PostgreSQL WASM through a
socket adapter:

```bash
cd devtools && npm ci && cd ..
ASKDB_PYTHON="$PWD/.venv/bin/python" node devtools/check-postgres.mjs
```

That runtime has one underlying database connection with multiplexed client
sockets. It does not verify native PostgreSQL concurrency or production pooling.

## Reproduce the model probe

```bash
python evaluate_agent.py --model "$ASKDB_LOCAL_MODEL" --model-name Qwen/Qwen3-1.7B
```

The evaluation starts a real localhost FastAPI/Uvicorn server and sends six
synthetic questions over HTTP. Expected answers are specified separately from
the model adapter; failed cases remain in the report. Host-control tests use
clearly labeled scripted model doubles. They are not LLM-accuracy measurements.

Architecture, limits and troubleshooting are under
`docs/`. Docker and CI configurations are supplied but not executed here.
No production deployment or real business impact is claimed.


## CPU Inference Decision Lab upgrade

See [the lab guide](inference_lab/README.md) for the measured one/four-thread
comparison on Qwen3-1.7B and [METRICS.md](METRICS.md) for results and limits.
Open `evidence/inference-profile/report.html` offline to filter runs and inspect
exact tool actions, SQL answers and strict failures. Raw CSV/JSON and pinned
environment are included. Model weights are excluded. This is local development
evidence, not production deployment or a generalized accuracy claim.


## Evidence-backed investigation workflow

See [the integration and evaluation guide](docs/INVESTIGATION_WORKFLOW.md). New authenticated endpoints `/analysis/tasks` and `/analysis/tasks/{request_id}` connect retrieval-grounded model planning, approved metric SQL, reconciliation, evidence reports and durable replay protection. The guide records seven of eight successful development API scenarios and the remaining grouping failure; raw results are under `evidence/investigation-workflow`.
