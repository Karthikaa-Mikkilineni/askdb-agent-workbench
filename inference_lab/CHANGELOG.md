# Inference lab change history

## 2026-10-27

* Added isolated-worker CPU inference replay with fixed schema/metric history.
* Added separate generation latency, TTFT, token throughput, token-cap and
  sampled process RSS measurements plus explicit warmup exclusion.
* Changed the planned main comparison from cache/no-cache to one/four CPU
  threads with cache enabled, after aborting the expensive uncached warmup.
* Corrected a PID-namespace memory attribution error before accepting final
  measurements. Kernel `/proc/self/status` now identifies the measured worker.
  Discarded observations are retained and excluded from the final comparison.
* Added strict financial-answer checks, paired prompt/output hashes, per-call
  CSV and an offline interactive report showing failures as well as successes.
* Added validated cache/thread settings to the existing model provider and
  server configuration; retained local deployment and existing guardrails.
* Added regression tests for financial correctness, mutation rejection,
  clarification, invalid actions, memory attribution and invalid settings.

No production deployment, external client collaboration, or generalized model
accuracy is established by these development measurements.
