import json, os, psycopg
from pathlib import Path
from urllib.request import Request, urlopen

API=os.getenv('ASKDB_API','http://localhost:8000/query'); DB=os.getenv('BENCHMARK_DB','postgresql://askdb_readonly:readonly@localhost:5432/askdb')

def norm(rows):
    def cv(v): return str(v) if v is not None else None
    return sorted([tuple(cv(v) for v in r) for r in rows])

def run_sql(conn, sql):
    with conn.cursor() as c: c.execute(sql); return c.fetchall()

def ask(q):
    req=Request(API,data=json.dumps({'question':q}).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req) as r:return json.load(r)

items=json.loads(Path(__file__).with_name('questions.json').read_text()); passed=0; details=[]
with psycopg.connect(DB) as conn:
    conn.execute('SET TRANSACTION READ ONLY')
    for x in items:
        try:
            gold=norm(run_sql(conn,x['gold_sql'])); out=ask(x['question']); pred=norm(run_sql(conn,out['sql']))
            ok=gold==pred; passed+=ok; details.append({'id':x['id'],'ok':ok,'generated_sql':out['sql']})
        except Exception as e: details.append({'id':x['id'],'ok':False,'error':str(e)})
result={'passed':passed,'total':len(items),'execution_accuracy':passed/len(items),'details':details}
Path(__file__).with_name('benchmark_results.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
