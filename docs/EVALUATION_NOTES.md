# How to interpret the evidence

`evidence/clean-environment-tests.log` covers original guard/schema tests plus the new
agent, policy, API and mocked hosted-provider checks. PostgreSQL tests skip in
that invocation and run separately in `evidence/postgres-tests.log`. Do not
count skipped cases as passing. The final totals are summarized in METRICS.md.

`evidence/browser-check.log` uses a **scripted UI model** to isolate rendering,
result display, clarification follow-up, reset and mobile layout. It is not
an LLM benchmark. The React build retains a large legacy syntax-highlighter
bundle warning; production bundle optimization was not performed.

`evidence/final-model-evaluation.json` uses **real Qwen3-1.7B CPU inference**
through an actual localhost HTTP service. It checks counts, booked revenue,
refund-adjusted revenue, region aggregation and an ambiguous revenue request.
Exact fixture answers are specified independently of the model. For the
ambiguous request, success requires clarification; merely executing plausible
SQL is a failure. Only six questions are tested, without a held-out prompt
development split, so this is a development probe, not a general accuracy claim.

Development evidence is retained:

* `initial-0.6B-development-probe.json`: a smaller model failed all six tasks
  under an earlier action protocol. It is not a controlled model comparison.
* `pre-structured-stop-evaluation.json`: Qwen3-1.7B completed two of six tasks
  before generation was restricted to one action per turn. Several responses
  contained multiple JSON actions and were rejected as malformed.
* `model-format-diagnostic.json`: actual raw model response illustrating that
  multi-action failure. The local adapter now stops decoding at the first
  complete JSON object, then waits for the real tool observation. The host
  still checks the action schema and permissions. It never executes a batch
  of speculative model-generated actions.
* `pre-grain-guard-evaluation.json`: the next full run exposed an executable
  but incorrect net-revenue result. This motivated the domain-specific grain
  guard. It is retained rather than hidden by the final rerun.
* `grain-guard-only-development-probe.json`: the guard blocked that pattern,
  while the small model still struggled with repair. The final implementation
  adds an approved one-row-per-order financial view and documented metric
  definitions, reducing the need for the model to reconstruct financial joins.
* `initial-postgres-single-socket-failure.log`: the initial embedded transport
  sometimes closed rapid reconnects when capped at one client socket. The
  harness now allows 16 multiplexed sockets over PGlite's single underlying
  connection. This is a test-harness setting, not native database concurrency
  evidence or a production retry guarantee.

Testing never demonstrates that arbitrary prompts, SQL or data are safe.
Read-only transactions and tool limits control capabilities; financial
definitions and join semantics still require human judgment and evaluation.
