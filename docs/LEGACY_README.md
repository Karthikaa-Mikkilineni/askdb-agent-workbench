# AskDB — NL2SQL Analytics Assistant

Full-stack NL2SQL portfolio project: React/TypeScript UI → FastAPI → schema introspection → OpenAI/Anthropic → SQLGlot safety validation → PostgreSQL read-only execution.

## Safety
- Dedicated PostgreSQL read-only role
- One-statement enforcement
- DDL/DML blocked by SQL AST validation
- Auto-LIMIT (100 rows) when absent
- 5-second database statement timeout
- Side-effect/locking constructs blocked

## Run
1. Copy `.env.example` to `.env` and add either an OpenAI or Anthropic API key.
2. `docker compose up --build`
3. UI: http://localhost:5173 — API docs: http://localhost:8000/docs

## 20-question execution benchmark
After the app is running:
`pip install psycopg[binary]`
`python benchmark/evaluate.py`

The evaluator compares the *executed result* of generated SQL with the executed result of a gold SQL query. It writes `benchmark/benchmark_results.json`. This is more robust than exact string matching because semantically equivalent SQL can differ textually.

No benchmark percentage is claimed until this evaluator is run against a configured LLM.
