import json
class QueryTooExpensive(ValueError): pass

def inspect_explain(conn,sql,max_total_cost=100000,max_plan_rows=1_000_000):
    row=conn.execute("EXPLAIN (FORMAT JSON) "+sql).fetchone()
    doc=row[0]
    if isinstance(doc,str):doc=json.loads(doc)
    plan=doc[0]["Plan"]
    cost=float(plan.get("Total Cost",0)); rows=int(plan.get("Plan Rows",0))
    if cost>max_total_cost or rows>max_plan_rows:
        raise QueryTooExpensive(f"Query plan exceeds budget: cost={cost}, rows={rows}")
    return {"total_cost":cost,"plan_rows":rows,"node_type":plan.get("Node Type")}
