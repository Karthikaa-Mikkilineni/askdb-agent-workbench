import json, os
from typing import Callable

SYSTEM="""You are a PostgreSQL analytics engineer.
Return JSON only with keys reasoning_summary and sql.
Use ONLY the supplied schema. Generate one read-only SELECT statement.
Never invent tables/columns. Prefer explicit JOIN conditions. Do not use DDL/DML."""

def prompt(question,schema,error=None,explain=None):
    repair=""
    if error: repair+=f"\nPrevious execution/validation error:\n{error}\nRepair the SQL."
    if explain: repair+=f"\nPostgreSQL EXPLAIN feedback:\n{explain}\nProduce a safer/cheaper equivalent if possible."
    return f"""{SYSTEM}

SCHEMA:
{schema}

QUESTION:
{question}
{repair}
"""

def parse_json_response(text):
    text=text.strip()
    if text.startswith("```"):
        text=text.strip("`")
        text=text[text.find("\n")+1:]
        if text.endswith("```"):text=text[:-3]
    obj=json.loads(text)
    return obj["sql"],obj.get("reasoning_summary","")

def generate(call_llm:Callable[[str],str],question,schema,error=None,explain=None):
    return parse_json_response(call_llm(prompt(question,schema,error,explain)))
