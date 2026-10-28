# Evidence-backed investigation workflow

## Implemented technologies
Python; PyTorch; Hugging Face Transformers; Qwen3-1.7B; LangGraph; FastAPI; SQL; SQLite FTS5/BM25; Pydantic; Pytest. PostgreSQL adapter integration was exercised on PGlite PostgreSQL 18.6. No LoRA, PEFT, fine-tuning, external-client delivery or cloud deployment is claimed.

## Business problem
A valid SQL query can answer the wrong financial question, multiply order totals across item/refund joins, or apply the wrong regional breakdown. This workflow constrains a proposed investigation to approved metrics and returns host-computed evidence rather than invented values.

## Workflow and safeguards
1. Retrieve metric definitions using SQLite FTS5/BM25.
2. Apply explicit capability rules: conversion needs unavailable exposure data; unspecified revenue needs a booked/net clarification. These two policies can stop a task without calling a model.
3. Generate a metric plan with Qwen3. Local generation uses a token-prefix trie compiled from valid catalog plans; hosted adapters retain validation and bounded retries but do not use this local decoder.
4. Enforce caller metric/group contracts and a step budget (default one; comparisons may request two to four). Explicit metric lists authorize their own length. The budget is a resource/intent boundary, not an oracle for the right metric.
5. Execute approved read-only SQL over one-row-per-order financial views. The model does not supply arbitrary SQL in this workflow; the original free-SQL agent remains separately available.
6. Verify output schemas, finite values, duplicate regions, row-cap risks, metadata stability, and regional-to-overall totals; publish a Markdown evidence report with metric citations and result hashes.

Completed, failed and clarification responses are stored in SQLite. Repeating the same request ID and payload returns the stored response without new inference. A changed payload with an existing ID returns HTTP 409. An in-progress record also returns a conflict; crash recovery does not silently rerun work. This is local request replay protection, not distributed exactly-once execution.

## Measured validation
- 139 Python checks passed; nine PostgreSQL-dependent tests were skipped in that run.
- All nine tests passed separately against PGlite PostgreSQL 18.6, including the new grouped financial investigation and replay. PGlite is embedded PostgreSQL compiled to WASM, not native multi-client load testing.
- Eight development scenarios ran over real localhost HTTP through FastAPI/Uvicorn. Six invoked real Qwen3 CPU inference; two were handled by explicit capability policies. Three requests supplied metric/group contracts, and the comparison supplied a two-step budget.
- Seven of eight scenarios matched literal fixture outcomes. The free-text regional comparison returned overall totals instead of a regional breakdown and remains a failure. Its response requires review because no explicit grouping contract was supplied.
- All eight duplicate requests returned the saved result with zero additional model calls.

These are reused development questions on a tiny synthetic commerce fixture, not a held-out model accuracy benchmark. The earlier unconstrained run passed 2/8; adding grammar and scope controls passed 5/8; the final budgeted run passed 7/8. Prompts, policies and constraints changed together after examining failures, so those figures are development history, not a controlled model-quality improvement experiment. Earlier runs remain in evidence/investigation-workflow/development.

## Run
From the project root, install backend/agent-requirements.txt and the PyTorch/Transformers CPU environment listed in evidence/investigation-workflow/environment.txt.

```bash
PYTHONPATH=backend python -m pytest agent_tests backend/tests inference_lab -q
python evaluate_investigations.py --model /absolute/path/to/qwen3-1.7b
```

For the authenticated server, set ASKDB_LOCAL_MODEL, ASKDB_STATE_DIR, and ASKDB_API_KEY (a generated secret of at least 24 characters), then:

```bash
PYTHONPATH=backend uvicorn agentic.api:app_factory --factory --host 127.0.0.1 --port 8000
```

POST /analysis/tasks with a bearer token and JSON:

```json
{"request_id":"regional-review-001","question":"Compare booked and net revenue by region","required_metrics":["booked_revenue","net_revenue"],"group_by":"region"}
```

GET /analysis/tasks/regional-review-001 retrieves the saved report. The existing /agent/query endpoint remains available. request_id is an idempotency identifier, not an authenticated user identity. A single shared API key does not establish tenant isolation. Checkpoint/audit files are local and unencrypted. No real client information is included.

## Integration acceptance and limits
Explicitly supply metric IDs and grouping when the business requirement is known; otherwise the output carries review_required. This flag is not a semantic accuracy certificate. Result hashes are evidence integrity references, not independent proof of correct business meaning. The grouped-vs-overall check may fail if a source changes between independent read transactions; it is not a consistent database snapshot.

Templates deliberately cover only five metrics and two grouping modes. This trades general NL2SQL flexibility for inspectable execution. The capability rules are narrow English-domain rules and can over-clarify; they are not a universal intent classifier. Region output is conservatively rejected at the adapter's 50-row limit.

Model: Qwen/Qwen3-1.7B, revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e; CPU bfloat16, four threads, KV cache, greedy decoding. Model weights are not distributed. No fine-tuning was performed.

References: https://huggingface.co/docs/transformers/main_classes/text_generation and https://reference.langchain.com/python/langgraph/graph/state/StateGraph/compile
