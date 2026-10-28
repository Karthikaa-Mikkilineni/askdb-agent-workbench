# Validation of AI-assisted implementation

This extension was authored with an AI coding assistant. Review evidence is
executable tests and actual observed outputs, not an assertion that AI code
is automatically trustworthy.

* Correctness: exact fixture answers, deliberate fanout counterexample,
  prerequisite/order checks, schema drift, state restart and read-only behavior.
* Security: parse SQL with SQLGlot; deny mutations, wildcard projections,
  unapproved tables/schemas/functions and recursive queries; bound outputs;
  reject extra tool/API arguments and arbitrary model URLs; require API key.
* Recovery: inject unknown columns, malformed JSON, invalid actions, stale
  query references and provider exceptions. Reject unsupported finalization.
* Maintainability: the new agent is a separate package and endpoint. Existing
  Python query code and data fixture remain available; no framework stack was
  silently swapped in professional experience.
* Performance: time real local evaluation, but do not call it a load test or
  extrapolate throughput. The model, hardware and limits affect latency.
* Limits: scripted model doubles prove host control paths, not LLM planning
  accuracy. Real inference runs are kept separately with unsuccessful cases.

During development an invalid JSON response was counted twice toward the
error budget. The failing test exposed it; accounting now occurs once at the
tool boundary. A TypeScript ES2020 `replaceAll` build failure was corrected to
a compatible regular expression. PostgreSQL embedded-runtime intermittency
was investigated separately; see METRICS.md for its actual status.

A real model run returned 365 for net revenue, where the fixture's expected
answer is 315. Inspection found a direct orders/refunds join that multiplied
order totals and excluded unrefunded orders. A narrow SQL grain guard now
rejects order-total sums over directly joined raw child tables, with explicit
pre-aggregation feedback. Tests cover both rejected raw joins and accepted
CTE/subquery pre-aggregation. This does not establish correctness for arbitrary
derived metrics or indirect CTE aliases.

This document records an individual implementation review. It does not claim
professional peer review, stakeholder collaboration, or approval by a client.


## Inference lab validation (2026-10-27)

AI-assisted profiling code was checked against actual model runs and kernel
counters. Numeric-PID memory sampling initially reported less than 1 MiB for a
loaded 1.7B model. Comparison with kernel-resolved `/proc/self/status` exposed
a PID-namespace attribution error. Those observations were discarded, the RSS
reader was corrected, and the complete comparison was rerun. A regression test
now rejects implausibly small resident memory readings.

Financial-answer tests reject executable but wrong metrics, extra output columns,
mutations and unsupported actions. Raw prompt/token hashes, token counts and
clock ordering were reconciled for all 24 accepted measured generations. The
report keeps 3/6 unique-question failures visible rather than equating JSON
validity, token agreement or the 89 passing software tests with model accuracy.
