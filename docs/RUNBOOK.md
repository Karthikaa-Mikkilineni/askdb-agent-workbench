# Local operations and troubleshooting

1. Missing API key: generate a random value of at least 24 characters. Keep it
   in the process environment, never in source control or the browser URL.
2. `model_unavailable`: verify configured endpoint/model/credential locally.
   The API intentionally does not return the provider's raw error body.
3. `budget_exhausted`: inspect tool trace for invalid JSON, wrong columns,
   unsafe SQL or repeated calls. Improve the model/prompt; do not disable SQL
   validation or increase limits blindly.
4. `needs_clarification`: send the answer with the returned thread_id. The React
   workbench does this automatically until a terminal result is returned.
5. `context_exhausted`: start a fresh thread with a precise question. Old
   checkpoint data is not automatically deleted; establish retention yourself.
6. Database error: verify schema/SELECT-only grants and timeout settings.
   SQLSTATE 42703 means an undefined column; inspect metadata and revise SQL.
7. Result looks plausible but wrong: compare metric definition, filters and
   join grain with source tables. Check refunded orders and item multiplicity.
8. Schema changed: re-inspect and validate. Never reuse a cached approval.

Local data and checkpoints contain SQL, questions and bounded result rows.
Restrict the state directory, do not commit it, and delete it when no longer
needed. It is not encrypted and is unsuitable for real personal/health data
without further controls. Synthetic demo data has no real customers.

The shared local API key does not establish user ownership of thread IDs.
Before any shared deployment, add per-user authorization, TLS, rate limits,
proper secret management, checkpoint retention/encryption, a DB connection
pool, end-to-end timeout/cancellation and monitoring. Prompt injection remains
possible at the semantic layer; read-only tools and allowlists reduce its
capabilities but do not certify safety.

The legacy `/query` endpoint has its original behavior and dependencies; the
new protections apply to `/agent/query`, not retroactively to the old server.
