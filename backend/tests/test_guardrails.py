from app.guardrails import validate_and_limit, UnsafeQuery

def test_adds_limit():
    assert "LIMIT 100" in validate_and_limit("SELECT * FROM customers")

def test_preserves_limit():
    assert "LIMIT 5" in validate_and_limit("SELECT * FROM customers LIMIT 5")

def test_blocks_delete():
    try: validate_and_limit("DELETE FROM customers")
    except UnsafeQuery: return
    assert False
