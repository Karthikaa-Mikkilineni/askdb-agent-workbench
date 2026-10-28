# Verification and measured results

Recorded 2026-10-26. All commerce records are synthetic: three customers,
four orders, five item rows and three refund rows. Approved financial view:
one row per order. Paid booked revenue is 350; paid net revenue is 315.
Joining raw item rows and summing order totals instead gives 650.

## Automated checks

| Verification | Observed result | Scope |
| --- | --- | --- |
| Clean-environment Python tests | 75 passed; 8 PostgreSQL tests skipped | Host controls, SQL, metric view, API, mock provider, original tests |
| Separate PostgreSQL-compatible tests | 8 passed | Real psycopg2 queries against PGlite PostgreSQL 18.6 |
| Total distinct passing automated checks | **83** | Skipped tests count only after their separate passing invocation |
| React/TypeScript build | Passed | Local build; retains legacy bundle-size warning |
| Headless browser checks | Passed | Results, clarification follow-up, reset, mobile fit, no page errors |

The browser fixture and host-control tests use explicitly scripted model
responses. They prove those software paths, not LLM accuracy. The hosted
provider adapter was checked with mocked HTTP responses, not paid inference.

## Real local model evaluation

Model: Qwen/Qwen3-1.7B, revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Transformers 5.21.0,
PyTorch 2.14.1+cpu, bfloat16, four CPU threads, greedy decoding, maximum 512
new tokens and generation stop at the first complete JSON action. Weights
are excluded from the archive. See model-manifest.json and environment.txt.

Transport: actual localhost HTTP requests to FastAPI/Uvicorn. The model
selects tools; these are not scripted evaluation responses. The local SQL
backend is SQLite for this probe. Expected rows are independent fixture
answers in evaluate_agent.py. PostgreSQL is tested separately.

**Task success: 3/6.** Failed cases: net, region_net, ambiguous.

| Case | Status | Returned rows | Correct | Model calls | Tool/format errors | Wall seconds |
| --- | --- | --- | --- | --- | --- | --- |
| order_count | completed | [[4]] | Pass | 4 | 0 | 34.611 |
| paid_count | completed | [[3]] | Pass | 4 | 0 | 42.140 |
| booked | completed | [[350]] | Pass | 5 | 0 | 72.422 |
| net | completed | [[350, 315]] | Fail | 5 | 0 | 78.406 |
| region_net | needs_clarification | No result | Fail | 5 | 1 | 56.897 |
| ambiguous | completed | [[350]] | Fail | 5 | 0 | 69.203 |

Median observed wall time: 63.050s.
These are individual CPU development runs, not a load test or latency SLA.
The exact-row rubric treats extra columns as a failure. In the net-revenue
case, the model returned both booked revenue (350) and the correct net revenue
(315); the extra booked column fails that strict output-shape check.

Six questions and prompt changes informed by these same fixtures do not
establish held-out accuracy. Executable SQL can remain semantically wrong.
Review failed cases and traces before using results; no production readiness
or generalized safety/accuracy percentage is claimed.

## Reproduction commands actually used

From the project root in this workspace:


```bash
PYTHONPATH=backend /tmp/askdb-clean-env/bin/p`hon -m p`est agent_tests backend/tests -q
ASKDB_CAPTURE_TRACE=evidence/postgres-recovery-trace.json ASKDB_PYTHON=/tmp/askdb-clean-env/bin/p`hon node devtools/check-postgres.mjs
cd frontend && npm run build
```

The separate model environment ran:


```bash
/tmp/askdb-agent-env/bin/p`hon evaluate_agent.py --model /tmp/askdb-qwen3-1.7 --model-name Qwen/Qwen3-1.7B --output evidence/final-model-evaluation.json
```

README.md gives portable setup commands. Tests were also run after installing
only agent-requirements.txt into a new virtual environment. The full package
versions are retained in evidence/environment.txt. Browser automation uses
Playwright with a separate Chromium executable and the scripted browser
fixture, not the local LLM.

## Limits and development evidence

PGlite is PostgreSQL compiled to WASM, with one underlying connection and
multiplexed client sockets. These checks are not native PostgreSQL multi-client
concurrency verification. Docker and GitHub Actions configurations are supplied
but were not executed here. No cloud or production deployment occurred.

Earlier failed model probes, a raw multi-action response and the initial
single-client-socket transport failure are retained. The evolution includes
one-action generation stopping, a limited raw-join grain guard, and an approved
financial view. See docs/EVALUATION_NOTES.md for scope and caveats. The view is
not a guarantee that the model selects the correct metric, filter, or question.

Checkpoint persistence is local and not encrypted. Shared-user authorization,
production monitoring, load testing and real stakeholder use remain outside
the demonstrated work. No professional code-review or collaboration claim
is inferred from this individual project.


## Inference Decision Lab — 2026-10-27

Local replay measurements, not full-agent or held-out accuracy. Model:
Qwen/Qwen3-1.7B (1,720,574,976 parameters), pinned revision above, CPU bfloat16,
greedy decoding, max 128 new tokens. Hardware: AMD EPYC 9V74 virtual CPU host,
9 visible CPUs, cgroup quota 8 CPU equivalents and 8 GiB RAM. Linux 6.18.55,
Python 3.12.14, torch 2.14.1+cpu, Transformers 5.21.0.

Two fresh sequential processes, one excluded warmup each, six fixed synthetic
financial decision contexts with two repetitions (24 measured generations).
Schema and metric tool observations are supplied; SQL execution is outside the
generation timing. The original application already defaulted to four threads;
this experiment validates configuration trade-offs, not an improvement over an
unmeasured prior deployment.

| Measurement | One thread, KV cache | Four threads, KV cache |
|---|---:|---:|
| Median generation latency | 35.302 s | 15.019 s |
| Median TTFT | 14.309 s | 5.654 s |
| Median generated tokens/s, including prefill | 1.146 | 2.678 |
| Maximum sampled process RSS | 4015.637 MiB | 4018.379 MiB |
| Strict answers per 6 unique contexts | 3/6 | 3/6 |
| Strict answers across repeated runs | 6/12 | 6/12 |
| Valid JSON actions | 12/12 | 12/12 |
| Generation caps hit | 0 | 0 |

Median paired generation speedup: **2.313x**. All 12 paired outputs had identical
generated token hashes. Four threads are faster on this host, with 2.742 MiB
more sampled peak RSS; that small memory difference is not a robust cross-host
memory claim. The model still fails net, regional-net and ambiguous questions.
A faster configuration is not a fix for those failures or an unattended-release
recommendation. Two repetitions are timing observations, not independent
accuracy samples. Fixed configuration order can introduce runtime/thermal drift.

TTFT excludes tokenization/network/loading. RSS uses `/proc/self/status` sampled
every 5 ms and includes weights, libraries and allocator, not just activations.
Separate `ru_maxrss` includes process loading; kernel accounting can differ
slightly from VmRSS. Peak RSS is approximately 3.92 GiB. No GPU/edge-device,
concurrent-load, production or cloud measurement is claimed.

The initial uncached warmup was aborted before timed request results. A separate
initial run used a numeric PID RSS reader that was invalid in this host's outer
`/proc` namespace; its observations are under inference-diagnostics and excluded
from these results. A kernel-resolved `/proc/self` reader corrected the issue.

Current regression run: **89 passed, 8 skipped**, 2.22 seconds. The eight skipped
checks require the separate PGlite transport; their historical passing evidence
is retained above, not relabeled as a fresh native PostgreSQL run.

Reproduction: `inference_lab/README.md`. Exact raw observations, environment, CSV,
comparison report, console output and measurement acceptance checks are under
`evidence/inference-profile/`.

Post-upgrade real local HTTP smoke test: order_count completed correctly through
four model calls, 33.903 s end to end. This is one integration
check, not a second inference benchmark or a generalized accuracy estimate.


## Applied investigation workflow — 2026-10-27

139 Python tests passed; nine PostgreSQL-dependent tests were skipped in that invocation. A separate PGlite PostgreSQL 18.6 run passed all nine integration tests. Eight real local HTTP scenarios yielded seven strict task successes and eight successful idempotent replays with zero additional model calls. Six scenarios invoked Qwen3; two used host capability-policy clarification. Three supplied explicit metric/group contracts and one supplied a two-step budget.

The failed regional comparison selected overall grouping instead of region; it remains in the raw results and is not counted as successful. No held-out accuracy, fine-tuning, production deployment or actual client participation is inferred. See `docs/INVESTIGATION_WORKFLOW.md` for request contracts, development iteration history, database limitations, sources and reproduction.
