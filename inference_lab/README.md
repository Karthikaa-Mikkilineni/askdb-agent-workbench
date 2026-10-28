# AskDB Inference Decision Lab

This upgrade studies a developer-facing question: which CPU inference setting
is faster **without changing financial SQL answers**? It replays AskDB's six
synthetic commerce questions at the decision point after schema and metric
tool observations have been supplied. This isolates one model decision from
network, graph checkpoints and SQL execution. It does not measure full-agent
planning, a held-out benchmark, simultaneous users or a production SLA.

## Reproduce

Use Python 3.12 and install `backend/agent-requirements.txt`, PyTorch CPU,
Transformers 5.21.0, and psutil 7.2.2 in an isolated environment. Exact versions
from the actual run are retained in `evidence/inference-profile/environment.txt`.
Download Qwen/Qwen3-1.7B at revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` using
`scripts/download-local-model.py`. Weights are not included in the archive.

From the project root:

```bash
python inference_lab/benchmark_inference.py \
  --model /absolute/path/to/qwen3-1.7b --threads 4 --repeats 2 \
  --max-tokens 128 --output evidence/inference-profile
python inference_lab/report.py evidence/inference-profile
PYTHONPATH=backend python -m pytest agent_tests backend/tests inference_lab -q
```

Open `evidence/inference-profile/report.html` locally. Filter cases or
configurations, inspect exact generated actions and see failed quality gates.
CSV and raw JSON preserve prompt/output hashes, counts, timing, caps, memory,
quality decisions and environment. The report has no external assets or CDN.

## Measurement contract

* Two sequential, fresh worker processes load the identical model, bfloat16
  dtype, greedy decoding and the same 128-token cap.
* `kv_cache_1t` uses one intra-op CPU thread; `kv_cache_4t` uses four. Both
  enable KV caching. The existing adapter defaulted to four threads. The
  experiment can recommend keeping that default or changing it based on
  measured speed and quality. An uncached warmup attempt was aborted before
  recording timed results because its cost was unsuitable for routine tests.
* Both workers perform one excluded warmup, then use the same shuffled
  six-context schedule with two repetitions. Repeats assess timing variability;
  they do not create 12 independent quality questions.
* Generation latency starts before `generate()` and ends after it returns.
  TTFT starts at generation entry and ends at the first emitted output token;
  it includes prefill, not tokenization, model loading or HTTP.
* Overall token/s divides all generated tokens by generation duration.
  Decode token/s excludes the first token and uses emitted token timestamps.
* Peak RSS is sampled at 5 ms intervals during each call; a separate process
  high-water mark includes loading. RSS includes the model, imported libraries,
  cache and allocator; it is not exact live-tensor memory. Sampling can miss
  brief peaks. This is CPU memory, not GPU VRAM.
  The implementation reads kernel-resolved `/proc/self/status` because this
  host mounts `/proc` from an outer PID namespace. An initial numeric-PID
  sampler attributed RSS to the wrong process; those discarded observations
  are retained under `evidence/inference-diagnostics`, not in comparisons.
* JSON stopping is identical across configurations. Token-cap hits are retained,
  not discarded. Prompt hashes must match when comparing paired runs.
* A strict question/row oracle checks proposed SQL against synthetic fixture
  answers after AskDB's read-only SQL guard. JSON validity and answer correctness
  are distinct. Extra columns fail exact shape checks. Ambiguity expects a
  nonempty clarification action. Wrong metric choices remain failures.

## Applying configurations to the local application

The existing model provider now takes validated `use_cache` and `threads`
constructor settings. FastAPI's application factory reads `ASKDB_USE_KV_CACHE`
(`0` or `1`, default `1`) and `ASKDB_CPU_THREADS` (`1`–`8`, default `4`). These are
server settings, not arbitrary client request fields. PyTorch thread settings
are process-global; launch separate processes to compare configurations.
This does not introduce multi-tenant scheduling or GPU serving.

## Interpreting the measurements

Explain why an executable query can be financially wrong, why the supplied
metric view prevents one-to-many fanout, and why the evaluator must separately
test correctness. Show a slower or incorrect example as well as the aggregate.
Use raw paired measurements for any speedup claim and state the baseline.
Report deployment accurately as local CPU execution.
The comparison includes a strict correctness gate: a faster setting is not
an unattended-use recommendation if any measured answer is wrong.

Future improvements need a separate held-out question set, randomized
configuration order across more hosts, concurrent-load tests, and richer
domain annotations. This experiment cannot establish those results.

References:
https://huggingface.co/docs/transformers/kv_cache
https://docs.pytorch.org/docs/stable/generated/torch.autograd.grad_mode.inference_mode.html
