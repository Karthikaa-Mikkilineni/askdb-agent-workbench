"""Small synthetic commerce fixture + read-only SQLite and PostgreSQL adapters."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

TABLES = {"customers", "orders", "order_items", "refunds", "order_financials"}
METRICS = {
    "booked_revenue": "Use SUM(order_financials.booked_revenue) WHERE status='paid'. Approved view: one row per order.",
    "net_revenue": "Use SUM(order_financials.net_revenue) WHERE status='paid'. The view pre-aggregates refunds and includes unrefunded orders.",
    "conversion": "Undefined: there are no exposure/visit denominators in this database",
    "grain_warning": "Prefer the approved order_financials view for financial metrics. Join customers via customer_id for region. Raw child joins can multiply revenue.",
}
DDL = """
CREATE TABLE customers(id INTEGER PRIMARY KEY, region TEXT NOT NULL);
CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
 status TEXT NOT NULL, total NUMERIC NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE order_items(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
 category TEXT NOT NULL, quantity INTEGER NOT NULL);
CREATE TABLE refunds(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), amount NUMERIC NOT NULL);
INSERT INTO customers VALUES(1,'East'),(2,'West'),(3,'East');
INSERT INTO orders VALUES(1,1,'paid',100,'2026-01-01'),(2,2,'paid',200,'2026-01-02'),
 (3,1,'cancelled',80,'2026-01-03'),(4,3,'paid',50,'2026-01-04');
INSERT INTO order_items VALUES(1,1,'A',1),(2,1,'B',2),(3,2,'A',1),(4,2,'C',1),(5,4,'B',1);
INSERT INTO refunds VALUES(1,1,10),(2,1,5),(3,2,20);
"""
FINANCIALS_VIEW = """
CREATE VIEW order_financials AS
SELECT o.id AS order_id,o.customer_id,o.status,o.total AS booked_revenue,
 COALESCE(r.refund_amount,0) AS refund_amount,
 o.total-COALESCE(r.refund_amount,0) AS net_revenue
FROM orders o LEFT JOIN
 (SELECT order_id,SUM(amount) AS refund_amount FROM refunds GROUP BY order_id) r
ON r.order_id=o.id;
"""
DDL += FINANCIALS_VIEW


def seed(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with sqlite3.connect(path) as conn:
            conn.executescript(DDL)
    # Add the approved view to an existing local demo without rewriting its data.
    with sqlite3.connect(path) as conn:
        conn.execute(FINANCIALS_VIEW.replace("CREATE VIEW ", "CREATE VIEW IF NOT EXISTS ", 1))


class SQLiteAnalytics:
    dialect = "sqlite"

    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=1)
        conn.execute("PRAGMA query_only=ON")
        counter = [0]
        def progress():
            counter[0] += 1
            return counter[0] > 5000
        conn.set_progress_handler(progress, 100)
        try:
            yield conn
        finally:
            conn.close()

    def schema(self):
        with self.connection() as conn:
            return {table: [{"name": r[1], "type": r[2]} for r in conn.execute(f'PRAGMA table_info("{table}")')]
                    for table in sorted(TABLES)}

    def explain(self, sql):
        with self.connection() as conn:
            return {"details": [list(r) for r in conn.execute("EXPLAIN QUERY PLAN " + sql)],
                    "cost_guard": "SQLite instruction budget, not PostgreSQL cost estimate"}

    def execute(self, sql):
        with self.connection() as conn:
            cur = conn.execute(sql)
            return {"columns": [d[0] for d in cur.description], "rows": [list(r) for r in cur.fetchmany(50)]}


class PostgresAnalytics:
    dialect = "postgres"

    def __init__(self, dsn, max_cost=10000):
        self.dsn, self.max_cost = dsn, max_cost

    @contextmanager
    def connection(self):
        import psycopg2
        conn = psycopg2.connect(self.dsn, connect_timeout=5)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("SET LOCAL statement_timeout = '2000ms'")
                    cur.execute("SET LOCAL lock_timeout = '500ms'")
                yield conn
        finally:
            conn.close()

    def schema(self):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT table_name,column_name,data_type FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=ANY(%s) ORDER BY table_name,ordinal_position",
                        (sorted(TABLES),))
            result = {}
            for table, name, typ in cur.fetchall():
                result.setdefault(table, []).append({"name": name, "type": typ})
            return result

    def explain(self, sql):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("EXPLAIN (FORMAT JSON) " + sql)
            plan = cur.fetchone()[0][0]["Plan"]
            if plan["Total Cost"] > self.max_cost:
                raise ValueError("Estimated query cost exceeds configured budget")
            return {"total_cost": plan["Total Cost"], "estimated_rows": plan["Plan Rows"]}

    def execute(self, sql):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            return {"columns": [d.name for d in cur.description],
                    "rows": json.loads(json.dumps(cur.fetchmany(50), default=str))}
