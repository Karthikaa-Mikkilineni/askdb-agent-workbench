"""Export an offline, inspectable inference decision report and raw CSV."""
import csv
import html
import json
from pathlib import Path
import sys

def build(folder):
    comparison=json.loads((folder/'comparison.json').read_text())
    runs=[json.loads((folder/(c+'.json')).read_text()) for c in comparison['summary']]
    rows=[dict(config=run['config'],**r) for run in runs for r in run['measurements']]
    fields=['config','case_id','repetition','prompt_tokens','generated_tokens','generation_seconds',
            'request_seconds','ttft_seconds','tokens_per_second','decode_tokens_per_second',
            'sampled_peak_rss_mib','rss_growth_mib','token_cap_hit']
    with (folder/'requests.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields+['correct','valid_action'])
        writer.writeheader()
        for r in rows:writer.writerow({**{k:r[k] for k in fields},**{k:r['quality'][k] for k in ['correct','valid_action']}})
    summaries=comparison['summary']
    summaries_html=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in [
        k,f"{s['median_generation_seconds']:.3f}",f"{s['median_ttft_seconds']:.3f}",
        f"{s['median_tokens_per_second']:.2f}",f"{s['sampled_peak_rss_mib']:.1f}",
        f"{s['correct']}/{s['requests']}"] )+'</tr>' for k,s in summaries.items())
    payload=json.dumps(rows).replace('</','<\\/')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AskDB Inference Decision Lab</title><style>
body{font:16px system-ui,sans-serif;max-width:1180px;margin:auto;padding:32px;background:#f4f7fb;color:#17253b}h1{font-size:34px;margin-bottom:6px}h2{font-size:22px}section{background:white;padding:24px;margin:20px 0;border-radius:12px;border:1px solid #d9e1ed}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #d9e1ed}th{background:#edf2f8}select{padding:8px;margin:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2f8;padding:16px;border-radius:8px}small,.muted{color:#4b5c76}.warning{border-left:5px solid #bd7221}button{border:0;background:#173e70;color:white;padding:7px 12px;border-radius:5px;cursor:pointer}.ok{color:#146743}.fail{color:#a32a30}.scroll{overflow:auto}.bar{height:12px;background:#2a69b8;border-radius:3px;min-width:2px}footer{margin:20px 0}</style>
<h1>AskDB Inference Decision Lab</h1><p class="muted">A speed–memory–correctness replay for financial SQL tool decisions</p>
<section class="warning"><b>Development evidence, not production accuracy.</b> Six fixed contexts supply schema and metric observations. Two repetitions per context measure timing repeatability, not independent accuracy. Greedy bfloat16 CPU inference; model load and network excluded from generation timing. Both configurations use KV caching. Only CPU thread count changes (one versus four).</section>
<section><h2>Measured configuration comparison</h2><div class="scroll"><table><thead><tr><th>Configuration</th><th>Median generation s</th><th>Median TTFT s</th><th>Median token/s</th><th>Peak sampled RSS MiB</th><th>Strict success</th></tr></thead><tbody>SUMMARY</tbody></table></div><p>TTFT: generation start to first emitted token. Token/s includes prefill. RSS includes model, libraries and allocator, sampled every 5 ms.</p></section>
<section><h2>Inspect a decision</h2><label>Case <select id="case"><option value="all">All cases</option></select></label><label>Configuration <select id="config"><option value="all">All configurations</option></select></label><div class="scroll"><table><thead><tr><th>Case / repetition</th><th>Config</th><th>Generation</th><th>Time</th><th>Strict result</th><th>Inspect</th></tr></thead><tbody id="body"></tbody></table></div><h3>Generated action and quality gate</h3><pre id="detail">Select Inspect to review the exact model output, SQL result and oracle decision.</pre></section>
<section><h2>How to read the trade-off</h2><p>A valid JSON action can still select the wrong metric, filter, join grain or output shape. The quality gate runs proposed SELECT statements through AskDB's read-only SQL guard and compares returned rows with independently specified fixture answers. Clarification is scored separately. Cache output agreement tests numerical stability on these contexts only.</p><p>See comparison.json, requests.csv, and both raw worker JSON files for every observation, token cap, prompt hash, environment and model revision. No scheduled refresh, concurrent service capacity, cloud deployment or hardware-accelerator result is implied.</p></section><footer class="muted">Synthetic commerce data · Local CPU benchmark · Reproducible commands in inference_lab/README.md</footer>
<script>const rows=PAYLOAD;const caseBox=document.getElementById('case'),configBox=document.getElementById('config');for(const [el,key] of [[caseBox,'case_id'],[configBox,'config']])for(const name of new Set(rows.map(r=>r[key]))){const o=document.createElement('option');o.value=name;o.textContent=name;el.append(o)}function render(){const body=document.getElementById('body');body.replaceChildren();const visible=rows.filter(r=>(caseBox.value==='all'||r.case_id===caseBox.value)&&(configBox.value==='all'||r.config===configBox.value));const max=Math.max(...rows.map(r=>r.generation_seconds));for(const r of visible){const tr=document.createElement('tr');for(const text of [r.case_id+' / '+r.repetition,r.config]){const td=document.createElement('td');td.textContent=text;tr.append(td)}const chart=document.createElement('td');const bar=document.createElement('div');bar.className='bar';bar.style.width=(140*r.generation_seconds/max)+'px';chart.append(bar);tr.append(chart);const time=document.createElement('td');time.textContent=r.generation_seconds.toFixed(3)+' s';tr.append(time);const q=document.createElement('td');q.textContent=r.quality.correct?'Pass':'Fail';q.className=r.quality.correct?'ok':'fail';tr.append(q);const last=document.createElement('td'),button=document.createElement('button');button.textContent='Inspect';button.onclick=()=>document.getElementById('detail').textContent=JSON.stringify(r,null,2);last.append(button);tr.append(last);body.append(tr)}}caseBox.onchange=configBox.onchange=render;render();</script></html>'''
    (folder/'report.html').write_text(page.replace('SUMMARY',summaries_html).replace('PAYLOAD',payload))
    print(folder/'report.html')

if __name__=='__main__':build(Path(sys.argv[1] if len(sys.argv)>1 else 'evidence/inference-profile'))
