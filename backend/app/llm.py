from openai import OpenAI
from anthropic import Anthropic
from .config import settings

SYSTEM = """You translate natural-language analytics questions into PostgreSQL SQL.
Return SQL only, no markdown. Use only tables/columns in the provided schema.
Generate exactly one read-only SELECT statement. Never modify data or schema.
Prefer explicit JOIN conditions and deterministic ordering when the question asks for top/bottom results."""

def generate_sql(question: str, schema: str) -> str:
    prompt = f"DATABASE SCHEMA:\n{schema}\n\nQUESTION:\n{question}\n\nPostgreSQL SQL:"
    if settings.llm_provider.lower() == "anthropic":
        client = Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(model=settings.anthropic_model, max_tokens=700,
            system=SYSTEM, messages=[{"role":"user","content":prompt}])
        return msg.content[0].text
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(model=settings.openai_model, temperature=0,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}])
    return resp.choices[0].message.content or ""
