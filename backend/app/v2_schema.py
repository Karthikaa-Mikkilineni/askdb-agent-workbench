from dataclasses import dataclass
from typing import Iterable
import re

@dataclass
class Table:
    schema:str
    name:str
    columns:list[dict]
    foreign_keys:list[dict]

def compact_schema(tables:list[Table], question:str, max_tables:int=8)->str:
    """Lightweight schema linker: lexical relevance + FK expansion."""
    q=set(re.findall(r"[a-z0-9_]+",question.lower()))
    scored=[]
    for t in tables:
        terms={t.name.lower(),*(str(c["name"]).lower() for c in t.columns)}
        score=len(q & terms)
        # substring signal catches "customer" vs customers/customer_id.
        score += sum(0.25 for token in q for term in terms if token in term or term in token)
        scored.append((score,t))
    chosen=[t for _,t in sorted(scored,key=lambda x:x[0],reverse=True)[:max_tables]]
    names={(t.schema,t.name) for t in chosen}
    # Add directly referenced FK neighbors where available.
    by={(t.schema,t.name):t for t in tables}
    for t in list(chosen):
        for fk in t.foreign_keys:
            key=(fk.get("foreign_schema","public"),fk["foreign_table"])
            if key in by and key not in names and len(chosen)<max_tables:
                chosen.append(by[key]); names.add(key)
    lines=[]
    for t in chosen:
        cols=", ".join(f'{c["name"]} {c["type"]}' for c in t.columns)
        lines.append(f"{t.schema}.{t.name}({cols})")
        for fk in t.foreign_keys:
            lines.append(f"  FK {fk['column']} -> {fk.get('foreign_schema','public')}.{fk['foreign_table']}.{fk['foreign_column']}")
    return "\n".join(lines)
