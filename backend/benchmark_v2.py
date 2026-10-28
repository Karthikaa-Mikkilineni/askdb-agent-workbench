"""Comparative NL2SQL benchmark.

Input JSONL:
{"question":"...", "gold_sql":"..."}

Evaluates:
A) direct prompt
B) schema-linked prompt
C) schema-linked + bounded repair

Execution accuracy is determined by comparing normalized result sets, not SQL strings.
Requires a configured test PostgreSQL database and LLM key/provider.
"""
import json, argparse, time

def canon(rows):
    return sorted([tuple(str(x) for x in r) for r in rows])

def execution_equal(conn,pred,gold):
    try:
        a=conn.execute(pred).fetchall()
        b=conn.execute(gold).fetchall()
        return canon(a)==canon(b)
    except Exception:return False

def summarize(records):
    n=len(records)
    out={"n":n}
    for mode in ["direct","schema_linked","repair"]:
        vals=[r[mode] for r in records]
        out[mode+"_execution_accuracy"]=sum(vals)/n if n else 0
    out["repair_successes"]=sum(r.get("repaired",False) for r in records)
    return out

if __name__=="__main__":
    print(__doc__)
