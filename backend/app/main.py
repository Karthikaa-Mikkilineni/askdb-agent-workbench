from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .schemas import QueryRequest, QueryResponse
from .database import get_schema_text, execute_readonly
from .llm import generate_sql
from .guardrails import validate_and_limit, UnsafeQuery

app = FastAPI(title="AskDB NL2SQL Assistant")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        schema = get_schema_text()
        raw = generate_sql(req.question, schema)
        safe_sql = validate_and_limit(raw)
        columns, rows = execute_readonly(safe_sql)
        return QueryResponse(question=req.question, sql=safe_sql, columns=columns, rows=rows, row_count=len(rows))
    except UnsafeQuery as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
