from sqlalchemy import create_engine, text
from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

def get_schema_text() -> str:
    sql = text("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='public'
        ORDER BY table_name, ordinal_position
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    tables = {}
    for r in rows:
        tables.setdefault(r['table_name'], []).append(
            f"{r['column_name']} {r['data_type']} nullable={r['is_nullable']}"
        )
    return "\n".join(f"TABLE {t}:\n  " + "\n  ".join(cols) for t, cols in tables.items())

def execute_readonly(sql: str):
    with engine.begin() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text(f"SET LOCAL statement_timeout = {int(settings.statement_timeout_ms)}"))
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(r) for r in result.mappings().all()]
    return columns, rows
