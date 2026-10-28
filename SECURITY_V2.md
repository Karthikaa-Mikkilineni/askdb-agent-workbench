# AskDB v2 security model

AskDB treats LLM-generated SQL as untrusted input.

1. PostgreSQL application credentials should be a dedicated **read-only role**.
2. SQL is parsed with SQLGlot; only a single SELECT/set-operation is accepted.
3. DDL/DML/administrative statements and selected dangerous PostgreSQL functions are rejected.
4. A row LIMIT is injected when absent.
5. `EXPLAIN (FORMAT JSON)` is checked before execution; queries above configured cost/row budgets are rejected.
6. Execution uses `transaction_read_only=on` and a 5-second `statement_timeout`.
7. Automatic repair is bounded (default: 2 repairs), preventing unbounded agent loops.
8. The model receives schema metadata and error text, not arbitrary database contents.
