from pydantic import BaseModel, Field
from typing import Any

class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)

class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
