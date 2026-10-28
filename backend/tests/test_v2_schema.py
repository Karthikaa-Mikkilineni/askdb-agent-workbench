from app.v2_schema import Table,compact_schema
def test_schema_linker_prefers_relevant_table():
    ts=[
      Table("public","customers",[{"name":"customer_id","type":"int"},{"name":"email","type":"text"}],[]),
      Table("public","orders",[{"name":"order_id","type":"int"},{"name":"revenue","type":"numeric"}],[])
    ]
    x=compact_schema(ts,"show order revenue",1)
    assert "orders" in x
