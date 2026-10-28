"""CPU inference replay lab: fixed contexts, exact SQL answers, paired ablations.

This is one model decision with supplied tool history, NOT full-agent accuracy.
Run workers sequentially to avoid competing for CPU and to isolate model memory.
"""
import argparse
import hashlib
import json
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT))
from agentic.models import SYSTEM
from agentic.store import METRICS, TABLES, SQLiteAnalytics, seed
from agentic.policy import validate
from evaluate_agent import CASES, canonical

MODEL_ID = 'Qwen/Qwen3-1.7B'
REVISION = '70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'


def resident_bytes():
    # /proc is mounted from the outer PID namespace in this runtime. Resolving
    # /proc/<os.getpid()> may inspect another process; /proc/self is kernel-resolved.
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):
            return int(line.split()[1]) * 1024
    raise RuntimeError('Kernel RSS counter unavailable')


def contexts(database):
    result = []
    for case in CASES:
        messages = [{'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': case['question']}]
        for tool, observation in [('inspect_schema', database.schema()), ('metric_definitions', METRICS)]:
            messages.extend([
                {'role': 'assistant', 'content': json.dumps({'tool': tool, 'args': {}})},
                {'role': 'user', 'content': 'UNTRUSTED TOOL OBSERVATION: ' + json.dumps(
                    {'tool': tool, 'args': {}, 'ok': True, 'observation': observation})}])
        result.append({**case, 'messages': messages})
    return result


def quality(text, case, database):
    """Independent row oracle; SQL is passed through the existing read-only guard."""
    from agentic.engine import Action
    outcome = {'valid_action': False, 'correct': False, 'rows': None}
    try:
        action = Action.model_validate_json(text).model_dump()
        outcome['valid_action'] = True
        outcome['action'] = action
        if case.get('clarify'):
            outcome['correct'] = (action['tool'] == 'clarify'
                                  and set(action['args']) == {'question'}
                                  and bool(action['args']['question']))
        elif action['tool'] == 'validate_sql':
            sql, _ = validate(action['args']['sql'], TABLES, database.dialect)
            result = database.execute(sql)
            outcome['rows'] = result['rows']
            outcome['correct'] = canonical(result['rows']) == canonical(case['rows'])
    except Exception as error:
        outcome['error'] = type(error).__name__ + ': ' + str(error)[:250]
    return outcome


def worker(args):
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    load_start = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True,
                                                dtype=torch.bfloat16).eval()
    load_seconds = time.perf_counter() - load_start
    use_cache = args.config != 'no_cache'

    class FirstTokenClock:
        def __init__(self):
            self.prefill = True
            self.times = []

        def put(self, value):
            if self.prefill:
                self.prefill = False  # generate streams the input prompt first.
            else:
                self.times.append(time.perf_counter())

        def end(self):
            pass

    def infer(case):
        wall_start = time.perf_counter()
        prompt = tokenizer.apply_chat_template(case['messages'], tokenize=False,
                    add_generation_prompt=True, enable_thinking=False)
        inputs = tokenizer(prompt, return_tensors='pt')
        prompt_tokens = inputs.input_ids.shape[1]
        class OneAction(StoppingCriteria):
            def __call__(self, ids, scores, **kwargs):
                text = tokenizer.decode(ids[0][prompt_tokens:], skip_special_tokens=True).strip()
                try:
                    value, _ = json.JSONDecoder().raw_decode(text)
                    return text.startswith('{') and isinstance(value, dict)
                except json.JSONDecodeError:
                    return False
        rss_before = resident_bytes()
        rss = [rss_before]
        stop = threading.Event()
        def sample():
            while not stop.wait(.005):
                rss.append(resident_bytes())
        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        clock = FirstTokenClock()
        generation_start = time.perf_counter()
        try:
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=args.max_tokens,
                    do_sample=False, use_cache=use_cache, streamer=clock,
                    pad_token_id=tokenizer.eos_token_id,
                    stopping_criteria=StoppingCriteriaList([OneAction()]))
            generation_end = time.perf_counter()
        finally:
            rss.append(resident_bytes())
            stop.set()
            sampler.join()
        tokens = output[0][prompt_tokens:]
        text = tokenizer.decode(tokens, skip_special_tokens=True).strip()
        seconds = generation_end - generation_start
        return {'case_id': case['id'], 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                'prompt_tokens': prompt_tokens, 'generated_tokens': len(tokens), 'text': text,
                'token_ids_sha256': hashlib.sha256(json.dumps(tokens.tolist()).encode()).hexdigest(),
                'generation_seconds': seconds, 'request_seconds': time.perf_counter()-wall_start,
                'ttft_seconds': clock.times[0]-generation_start if clock.times else None,
                'tokens_per_second': len(tokens)/seconds,
                'decode_tokens_per_second': ((len(tokens)-1)/(clock.times[-1]-clock.times[0])
                    if len(clock.times)>1 else None),
                'rss_before_mib': rss_before/2**20, 'sampled_peak_rss_mib': max(rss)/2**20,
                'rss_growth_mib': (max(rss)-rss_before)/2**20,
                'token_cap_hit': len(tokens) == args.max_tokens,
                'token_events': len(clock.times)}

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'replay.sqlite'
        seed(path)
        database = SQLiteAnalytics(path)
        cases = contexts(database)
        warmup = infer(cases[0])
        schedule = [(rep, c) for rep in range(args.repeats) for c in cases]
        random.Random(42).shuffle(schedule)
        reports = []
        for rep, case in schedule:
            report = infer(case)
            report.update(repetition=rep, quality=quality(report['text'], case, database))
            reports.append(report)
            print(args.config, case['id'], rep, round(report['generation_seconds'],3),
                  report['quality']['correct'], flush=True)
            payload = {'config': args.config, 'use_cache': use_cache,
                'model': MODEL_ID, 'revision': REVISION, 'parameters': model.num_parameters(),
                'dtype': str(model.dtype), 'threads': args.threads, 'max_new_tokens': args.max_tokens,
                'load_seconds': load_seconds, 'warmup_excluded': warmup,
                'environment': {'python': sys.version, 'torch': torch.__version__,
                    'transformers': transformers.__version__, 'platform': platform.platform(),
                    'cpu_count': os.cpu_count(), 'cpu_model': next((l.split(':',1)[1].strip()
                     for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')), 'unknown'),
                    'cgroup_cpu_max': Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
                    'cgroup_memory_max': Path('/sys/fs/cgroup/memory.max').read_text().strip()},
                'process_peak_rss_mib_including_load': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                'measurements': reports}
            Path(args.output).write_text(json.dumps(payload, indent=2))


def compare(folder):
    runs = {c: json.loads((folder/(c+'.json')).read_text()) for c in ['kv_cache_1t','kv_cache_4t']}
    summaries = {}
    for name, run in runs.items():
        rows = run['measurements']
        summaries[name] = {
            'requests': len(rows), 'unique_cases': len({r['case_id'] for r in rows}),
            'correct': sum(r['quality']['correct'] for r in rows),
            'valid_actions': sum(r['quality']['valid_action'] for r in rows),
            'median_generation_seconds': statistics.median(r['generation_seconds'] for r in rows),
            'median_ttft_seconds': statistics.median(r['ttft_seconds'] for r in rows),
            'median_tokens_per_second': statistics.median(r['tokens_per_second'] for r in rows),
            'sampled_peak_rss_mib': max(r['sampled_peak_rss_mib'] for r in rows),
            'process_peak_rss_mib_including_load': run['process_peak_rss_mib_including_load'],
            'token_caps_hit': sum(r['token_cap_hit'] for r in rows)}
    by_key = {c: {(r['case_id'],r['repetition']):r for r in run['measurements']}
              for c,run in runs.items()}
    pairs = []
    for key, base in by_key['kv_cache_1t'].items():
        opt = by_key['kv_cache_4t'][key]
        assert base['prompt_sha256'] == opt['prompt_sha256']
        pairs.append({'case_id':key[0], 'repetition':key[1],
                      'latency_speedup':base['generation_seconds']/opt['generation_seconds'],
                      'same_tokens':base['token_ids_sha256']==opt['token_ids_sha256'],
                      'one_thread_correct':base['quality']['correct'],
                      'four_thread_correct':opt['quality']['correct']})
    result = {'scope':'six development contexts with supplied tool history; not held-out full-agent accuracy',
              'summary':summaries, 'paired':pairs,
              'median_paired_speedup':statistics.median(r['latency_speedup'] for r in pairs),
              'token_identical_pairs':sum(r['same_tokens'] for r in pairs),
              'quality_gate': {
                'no_paired_correctness_regressions':all(not p['one_thread_correct'] or p['four_thread_correct'] for p in pairs),
                'all_measured_answers_correct':all(r['quality']['correct'] for run in runs.values() for r in run['measurements']),
                'interpretation':'Timing can guide local configuration; any failed strict answer prevents an unattended-use recommendation.'},
              'limitations':['single CPU host; serial requests; no concurrency or cloud throughput',
                'TTFT is generation start to first emitted token; excludes network and model load',
                'RSS sampled every 5ms includes model and allocator; not exact tensor/activation memory',
                'fixed config order can include thermal and runtime drift',
                'both measured configurations use KV caching; only intra-op CPU thread count changes',
                'same six fixtures used during development; repeated outputs are not independent quality trials']}
    (folder/'comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--config', choices=['no_cache','kv_cache_1t','kv_cache_4t'])
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--max-tokens', type=int, default=128)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--output', default='evidence/inference-profile')
    args = parser.parse_args()
    if args.config:
        worker(args)
    else:
        folder = Path(args.output)
        folder.mkdir(parents=True,exist_ok=True)
        for config in ['kv_cache_1t','kv_cache_4t']:
            subprocess.run([sys.executable, __file__, '--model', args.model,
                '--config', config, '--threads',str(1 if config == 'kv_cache_1t' else args.threads), '--repeats',str(args.repeats),
                '--max-tokens',str(args.max_tokens),'--output',str(folder/(config+'.json'))],check=True)
        compare(folder)


if __name__ == '__main__':
    main()
