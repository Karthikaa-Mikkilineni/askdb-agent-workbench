import pytest
from agentic.policy import PolicyError, validate
from agentic.store import TABLES


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders", "UPDATE orders SET total=0", "DROP TABLE orders",
    "SELECT id INTO stolen FROM orders", "SELECT id FROM orders FOR UPDATE",
    "SELECT pg_read_file('/etc/passwd')", "SELECT pg_sleep(10)",
    "SELECT id FROM pg_catalog.pg_user", "SELECT id FROM private.orders",
    "SELECT id FROM missing", "SELECT * FROM orders", "SELECT o.* FROM orders o",
    "SELECT id FROM orders; DELETE FROM orders", "COPY orders TO '/tmp/out'",
    "SELECT set_config('role','postgres',false)", "SELECT load_extension('evil')",
    "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT n FROM x",
])
def test_rejects_unsafe_sql(sql):
    with pytest.raises(PolicyError):
        validate(sql, TABLES)


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) AS n FROM orders", "SELECT id FROM orders LIMIT 1000000",
    "SELECT id FROM orders UNION SELECT id FROM customers",
    "WITH paid AS (SELECT id,total FROM orders WHERE status='paid') SELECT SUM(total) FROM paid",
    "SELECT c.region,SUM(o.total) FROM orders o JOIN customers c ON c.id=o.customer_id GROUP BY c.region",
])
def test_valid_queries_are_bounded(sql, database):
    safe, token = validate(sql, TABLES, "sqlite", row_limit=2)
    assert len(database.execute(safe)["rows"]) <= 2
    assert len(token) == 64


def test_readonly_database_blocks_direct_mutation(database):
    with pytest.raises(Exception, match="readonly"):
        database.execute("DELETE FROM orders")


@pytest.mark.parametrize("sql", [
    "SELECT SUM(o.total)-SUM(r.amount) FROM orders o JOIN refunds r ON r.order_id=o.id",
    "SELECT SUM(total) FROM orders JOIN order_items i ON i.order_id=orders.id",
])
def test_revenue_grain_guard_rejects_raw_child_join(sql):
    with pytest.raises(PolicyError, match="grain"):
        validate(sql, TABLES, "sqlite")


@pytest.mark.parametrize("sql", [
    "WITH r AS (SELECT order_id,SUM(amount) AS amount FROM refunds GROUP BY order_id) "
    "SELECT SUM(o.total-COALESCE(r.amount,0)) FROM orders o LEFT JOIN r ON r.order_id=o.id WHERE o.status='paid'",
    "SELECT SUM(o.total-COALESCE(r.amount,0)) FROM orders o LEFT JOIN "
    "(SELECT order_id,SUM(amount) AS amount FROM refunds GROUP BY order_id) r ON r.order_id=o.id WHERE o.status='paid'",
])
def test_revenue_grain_guard_allows_preaggregation(sql, database):
    safe, _ = validate(sql, TABLES, "sqlite")
    assert database.execute(safe)["rows"] == [[315]]


def test_approved_financial_view_has_one_row_per_order(database):
    rows = database.execute("SELECT order_id,booked_revenue,refund_amount,net_revenue FROM order_financials ORDER BY order_id")["rows"]
    assert rows == [[1,100,15,85],[2,200,20,180],[3,80,0,80],[4,50,0,50]]


def test_approved_view_revenue_by_region(database):
    sql, _ = validate("SELECT c.region,SUM(f.net_revenue) FROM order_financials f "
                      "JOIN customers c ON c.id=f.customer_id WHERE f.status='paid' GROUP BY c.region ORDER BY c.region", TABLES, "sqlite")
    assert database.execute(sql)["rows"] == [["East",135],["West",180]]


def test_seed_adds_view_without_resetting_existing_demo(database):
    import sqlite3
    from agentic.store import seed
    with sqlite3.connect(database.path) as conn:
        conn.execute("DROP VIEW order_financials")
    seed(database.path)
    assert database.execute("SELECT COUNT(*) FROM order_financials")["rows"] == [[4]]
