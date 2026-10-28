import re, sqlglot
from sqlglot import exp

BLOCKED=(exp.Insert,exp.Update,exp.Delete,exp.Create,exp.Drop,exp.Alter,exp.Command,
         exp.Merge,exp.TruncateTable,exp.Copy)

class UnsafeSQL(ValueError): pass

def validate_and_limit(sql:str, max_rows:int=100)->str:
    if not sql or ";" in sql.strip().rstrip(";"):
        raise UnsafeSQL("Exactly one statement is allowed.")
    try: tree=sqlglot.parse_one(sql,read="postgres")
    except Exception as e: raise UnsafeSQL(f"Invalid SQL: {e}")
    if not isinstance(tree,(exp.Select,exp.Union,exp.Intersect,exp.Except)):
        raise UnsafeSQL("Only read-only SELECT queries are allowed.")
    if any(tree.find(x) is not None for x in BLOCKED):
        raise UnsafeSQL("Mutating/administrative SQL is blocked.")
    # Defense in depth against dangerous functions/file/network primitives.
    lowered=sql.lower()
    forbidden=["pg_read_file","pg_ls_dir","dblink","lo_import","lo_export","pg_sleep"]
    if any(x in lowered for x in forbidden): raise UnsafeSQL("Unsafe PostgreSQL function blocked.")
    if isinstance(tree,exp.Select) and tree.args.get("limit") is None:
        tree=tree.limit(max_rows)
    return tree.sql(dialect="postgres")
