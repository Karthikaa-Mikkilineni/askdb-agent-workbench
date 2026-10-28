import pytest
from app.v2_guardrails import validate_and_limit,UnsafeSQL

def test_select_gets_limit():
    s=validate_and_limit("SELECT id,name FROM customers")
    assert "LIMIT 100" in s.upper()

@pytest.mark.parametrize("sql",[
    "DELETE FROM customers","UPDATE customers SET name='x'",
    "DROP TABLE customers","SELECT pg_read_file('/etc/passwd')"
])
def test_mutation_and_unsafe_functions_blocked(sql):
    with pytest.raises(UnsafeSQL):validate_and_limit(sql)

def test_existing_limit_preserved():
    s=validate_and_limit("SELECT * FROM customers LIMIT 5")
    assert "LIMIT 5" in s.upper()
