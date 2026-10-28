"""Fail-closed SQL policy; database privileges remain the final boundary."""
import hashlib
import sqlglot
from sqlglot import exp


class PolicyError(ValueError):
    pass


FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "ROUND", "ABS",
             "LOWER", "UPPER", "LENGTH", "CAST", "EXTRACT", "DATE_TRUNC",
             "ROW_NUMBER", "RANK", "DENSE_RANK", "NULLIF"}


def validate(sql: str, tables: set[str], dialect="postgres", row_limit=50):
    if not isinstance(sql, str) or len(sql) > 8000:
        raise PolicyError("SQL must be text of at most 8000 characters")
    try:
        trees = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        raise PolicyError("SQL parse error") from exc
    if len(trees) != 1 or not isinstance(trees[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise PolicyError("Exactly one SELECT query is permitted")
    tree = trees[0]
    blocked = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
               exp.Command, exp.Merge, exp.Copy, exp.Into, exp.Lock, exp.Star)
    if any(isinstance(node, blocked) for node in tree.walk()):
        # COUNT(*) is useful, but all projected stars are rejected below instead.
        for node in tree.walk():
            if isinstance(node, exp.Star) and isinstance(node.parent, exp.Count):
                continue
            if isinstance(node, blocked):
                raise PolicyError("Mutation, locking, SELECT INTO, and wildcard projections are forbidden")
    if any(cte.args.get("recursive") for cte in tree.find_all(exp.With)):
        raise PolicyError("Recursive queries are forbidden")
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.catalog or (table.db and table.db != "public"):
            raise PolicyError("Only the public analytics schema is permitted")
        if table.name not in tables | ctes or not isinstance(table.this, exp.Identifier):
            raise PolicyError("Table is outside the analytics allowlist")
    for fun in tree.find_all(exp.Func):
        name = fun.name.upper() if isinstance(fun, exp.Anonymous) else fun.sql_name().upper()
        if name not in FUNCTIONS:
            raise PolicyError("Function is outside the analytics allowlist")
    # Domain-specific metric contract, deliberately narrow: an order total is
    # not additive after a direct join to its one-to-many items or refunds.
    for select in tree.find_all(exp.Select):
        source = select.args.get("from_")
        direct = ([source.this] if source else []) + [join.this for join in select.args.get("joins", [])]
        direct = [table for table in direct if isinstance(table, exp.Table)]
        order_aliases = {table.alias_or_name for table in direct if table.name == "orders"}
        raw_children = {table.name for table in direct if table.name in {"refunds", "order_items"}}
        if order_aliases and raw_children:
            for total in select.find_all(exp.Sum):
                if total.find_ancestor(exp.Select) is not select:
                    continue
                if any(col.name == "total" and (not col.table or col.table in order_aliases)
                       for col in total.find_all(exp.Column)):
                    raise PolicyError("Revenue grain check: SUM(orders.total) joins raw child rows; "
                                      "pre-aggregate refunds/items by order_id before joining")
    # Outer wrapper caps UNIONs and explicit oversized LIMITs as well as SELECTs.
    canonical = tree.sql(dialect=dialect)
    bounded = f"SELECT * FROM ({canonical}) AS askdb_result LIMIT {int(row_limit)}"
    return bounded, hashlib.sha256(bounded.encode()).hexdigest()
