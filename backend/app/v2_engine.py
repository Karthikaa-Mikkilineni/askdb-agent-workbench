import time
from .v2_guardrails import validate_and_limit,UnsafeSQL
from .v2_cost import inspect_explain,QueryTooExpensive
from .v2_planner import generate

def askdb_query(conn,call_llm,question,schema,max_repairs=2,statement_timeout_ms=5000):
    """Plan → validate → EXPLAIN → execute, with bounded automatic SQL repair."""
    error=None; explain_feedback=None
    attempts=[]
    for attempt in range(max_repairs+1):
        raw,summary=generate(call_llm,question,schema,error,explain_feedback)
        rec={"attempt":attempt+1,"generated_sql":raw,"reasoning_summary":summary}
        try:
            sql=validate_and_limit(raw,100)
            plan=inspect_explain(conn,sql)
            rec["plan"]=plan
            with conn.transaction():
                conn.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
                conn.execute("SET LOCAL transaction_read_only = on")
                t=time.perf_counter()
                cur=conn.execute(sql)
                rows=cur.fetchall()
                elapsed=(time.perf_counter()-t)*1000
                cols=[d.name for d in cur.description] if cur.description else []
            rec["status"]="success"; attempts.append(rec)
            return {"sql":sql,"columns":cols,"rows":rows,"execution_ms":round(elapsed,2),
                    "plan":plan,"attempts":attempts}
        except (UnsafeSQL,QueryTooExpensive,Exception) as e:
            # Bounded repair: feed only the error text, never database contents.
            error=str(e)[:1000]; rec["status"]="failed"; rec["error"]=error; attempts.append(rec)
    raise RuntimeError({"message":"Unable to produce a safe executable query","attempts":attempts})
