# AskDB v2 — Safe Agentic NL2SQL Analytics

This second engineering pass upgrades the original full-stack AskDB into a bounded NL2SQL agent:

`Question → schema linking → SQL generation → AST safety → EXPLAIN cost check → execution → error feedback → bounded repair`

## What changed
- schema linker selects question-relevant tables/columns and expands foreign-key neighbors
- structured JSON generation instead of scraping free-form model output
- SQLGlot AST validation and single-statement enforcement
- DDL/DML + dangerous PostgreSQL function blocking
- automatic `LIMIT 100`
- database-level read-only transaction + 5-second statement timeout
- `EXPLAIN (FORMAT JSON)` query-cost / plan-row budgets
- bounded SQL repair loop (maximum two repairs)
- comparative benchmark scaffold for **direct prompting vs schema-linked prompting vs schema-linked + repair**
- execution accuracy compares result sets against gold SQL rather than string similarity

## Benchmark integrity
The original project contains 20 question/SQL pairs. `backend/benchmark_v2.py` is the v2 evaluation harness. A real execution-accuracy percentage requires:
1. the benchmark PostgreSQL database,
2. an OpenAI/Anthropic API key,
3. running all three strategies against the same 20 questions.

No percentage is hard-coded in this repository. Report execution-accuracy results only after completing that controlled run.

## Execution architecture
This version is intentionally bounded rather than an unconstrained "agent": every generated query must pass deterministic validation and PostgreSQL planning checks before it can execute, and repair attempts are capped.
