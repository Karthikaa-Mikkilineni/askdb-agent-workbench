# AskDB agent extension

## Decision loop and boundaries

The LLM selects one structured action per turn. A LangGraph StateGraph routes
`decide -> tool -> decide` until completion, clarification, provider failure or a
budget limit. This differs from the legacy fixed SQL-generation/repair flow:
the model chooses whether to inspect metadata, consult metric definitions,
validate a new query, request a plan, execute, ask a human, or finish.

The host validates JSON with Pydantic and rejects undocumented arguments.
Allowed tools have no shell, filesystem, HTTP browsing, or write access.
Inspection precedes validation; validation precedes a successful EXPLAIN;
execution uses the exact host-held SQL, not fresh model-supplied SQL. A SHA-256
token binds canonical SQL to the inspected schema. The model does not need to
copy this token: EXPLAIN/execute address the current host-held validated query.
An optional SQL argument to EXPLAIN/execute must match the stored source or
bounded SQL exactly; it cannot replace it. Successful execution completes a
single-query job without an extra model-written final answer. Changing SQL
clears EXPLAIN approval and prior execution evidence. Schema
fingerprints are rechecked before EXPLAIN and execution. There is still a
time-of-check/time-of-use window between schema inspection and execution;
database errors and least-privilege transactions are the final boundary.

No free-form model-written final numeric answer is accepted. Completed output
is the actual SQL, result columns/rows and an evidence hash computed by the
host. This prevents invented output values, but **does not prove the SQL is
semantically correct**. A plausible executable query can still have wrong
filters, join grain, or business assumptions.

## Distinctive problem: grain and metric ambiguity

The synthetic fixture intentionally has orders with multiple items and multiple
refunds. Booked paid revenue is 350. Joining orders to items and summing order
totals produces 650, despite valid SQL. Correct net revenue is 315, after
pre-aggregating refunds by order. The metric-definitions tool documents these
contracts and explicitly states conversion cannot be computed without an
exposure denominator. Whether a model follows that guidance is measured, not
assumed. A narrow host-side revenue-grain guard rejects SUM(orders.total)
when the same SELECT directly joins raw order_items or refunds. It permits
child pre-aggregation through a CTE or subquery. This catches the demonstrated
fanout pattern; it is not a proof of grain correctness. CTEs that merely rename
raw children, other derived metrics, incorrect filters and missing LEFT JOINs
can still evade this limited rule. There is no heuristic declaring every join safe.

An approved `order_financials` view now exposes booked revenue, aggregated
refunds and net revenue with exactly one row per order. It LEFT JOINs refund
totals so orders without refunds remain present. Metric definitions direct
the model to this view and specify the paid-order filter. Region questions
can join it to customers without rebuilding a one-to-many financial join.
SQLite and PostgreSQL-compatible tests verify its arithmetic. The model still
chooses its query; the view does not guarantee that it selects the right filter.

## State and recovery

SqliteSaver persists graph state by UUID thread. Pending clarification history
survives Agent recreation. A completed job starts a new question context; only
pending clarification reuses prior messages. Each turn resets call/error
budgets. This is conversation continuity, **not exactly-once execution** or
an authenticated multi-user session store. All database tools are read-only.
The local service serializes runs with a process lock; no distributed-worker
or concurrent-throughput claim is made.

Defaults: 12 model calls, 3 tool/format failures, 24,000 characters of message
context, 2,000 question characters, 8,000 SQL characters and 50 result rows.
Hosted requests have a 45-second HTTP timeout. PostgreSQL queries have 2-second
statement and 500ms lock timeouts and a configured EXPLAIN cost ceiling.
SQLite uses a VM-instruction budget. Cost estimates can be inaccurate, so
they are admission checks rather than guarantees of runtime or correctness.

## Deployment status

Implemented as a FastAPI service with optional React workbench, a local
Transformers/PyTorch provider and a hosted OpenAI-compatible provider adapter.
Local tests and model-evaluation evidence are recorded in METRICS.md. Docker
and native PostgreSQL GitHub Actions configurations are supplied but have not
been executed here. No public cloud deployment, production users, SLA, or
production-grade model reliability is claimed.

Framework reference: https://docs.langchain.com/oss/python/langgraph/quickstart
