"""Dedicated empty TEST database only. Never point at an existing application DB."""
import os
import sys
from pathlib import Path
import psycopg2
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from agentic.store import DDL
with psycopg2.connect(os.environ["ASKDB_ADMIN_DSN"]) as conn, conn.cursor() as cur:
    cur.execute(DDL)
    cur.execute("CREATE ROLE askdb_reader LOGIN PASSWORD 'ci-test-only'")
    cur.execute("GRANT USAGE ON SCHEMA public TO askdb_reader")
    cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO askdb_reader")
