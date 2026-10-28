import re
import sqlglot
from sqlglot import exp
from .config import settings

FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command, exp.Merge)

class UnsafeQuery(ValueError): pass

def clean_llm_sql(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip().rstrip(";")

def validate_and_limit(raw: str) -> str:
    sql = clean_llm_sql(raw)
    if ";" in sql:
        raise UnsafeQuery("Multiple statements are not allowed")
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as e:
        raise UnsafeQuery(f"Invalid SQL: {e}") from e
    if isinstance(parsed, FORBIDDEN) or any(parsed.find(t) for t in FORBIDDEN):
        raise UnsafeQuery("Only read-only SELECT queries are allowed")
    if not isinstance(parsed, (exp.Select, exp.Union, exp.With, exp.Subquery)) and parsed.find(exp.Select) is None:
        raise UnsafeQuery("Query must contain SELECT")
    # Block common side-effect / file / lock constructs even when parser accepts them.
    lowered = sql.lower()
    blocked_tokens = [" for update", " pg_sleep(", "copy ", "into outfile", "lo_export("]
    if any(tok in lowered for tok in blocked_tokens):
        raise UnsafeQuery("Unsafe SQL construct blocked")
    if parsed.args.get("limit") is None:
        parsed = parsed.limit(settings.max_rows)
    return parsed.sql(dialect="postgres")
