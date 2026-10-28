"""Local prototype API, deliberately separate from the legacy /query server."""
import os
import secrets
from pathlib import Path
from uuid import UUID
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .engine import Agent
from .models import LocalTransformersModel, OpenAICompatibleModel
from .store import PostgresAnalytics, SQLiteAnalytics, seed


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    thread_id: UUID | None = None


def create_app(agent, api_key, investigation=None):
    if len(api_key) < 24:
        raise ValueError("ASKDB_API_KEY must be at least 24 characters")
    def authorize(authorization: str = Header(default="")):
        if not secrets.compare_digest(authorization, "Bearer " + api_key):
            raise HTTPException(401, "Invalid API credentials")
    app = FastAPI(title="AskDB Agentic SQL", dependencies=[Depends(authorize)])

    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "local prototype"}

    @app.post("/agent/query")
    def query(req: Request):
        try:
            return agent.run(req.question, str(req.thread_id) if req.thread_id else None)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if investigation is not None:
        from .investigations import attach_investigation_routes
        attach_investigation_routes(app, investigation)
    return app


def app_factory():
    folder = Path(os.environ.get("ASKDB_STATE_DIR", ".agent-state"))
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = os.environ.get("ASKDB_API_KEY", "")
    if len(key) < 24:
        raise ValueError("Set ASKDB_API_KEY to a random value of at least 24 characters")
    if os.environ.get("ASKDB_POSTGRES_DSN"):
        database = PostgresAnalytics(os.environ["ASKDB_POSTGRES_DSN"])
    else:
        seed(folder / "analytics.sqlite")
        database = SQLiteAnalytics(folder / "analytics.sqlite")
    if os.environ.get("ASKDB_LOCAL_MODEL"):
        cache = os.environ.get('ASKDB_USE_KV_CACHE', '1')
        if cache not in {'0', '1'}:
            raise ValueError('ASKDB_USE_KV_CACHE must be 0 or 1')
        model = LocalTransformersModel(os.environ["ASKDB_LOCAL_MODEL"],
            use_cache=cache == '1', threads=int(os.environ.get('ASKDB_CPU_THREADS', '4')))
    else:
        model = OpenAICompatibleModel(os.environ["ASKDB_LLM_BASE_URL"], os.environ["ASKDB_LLM_MODEL"],
                                      os.environ["ASKDB_LLM_API_KEY"])
    from .investigations import InvestigationWorkflow, PLAN_SYSTEM, CatalogConstrainedPlanner
    planner = CatalogConstrainedPlanner(model) if isinstance(model,LocalTransformersModel) else lambda messages:model.complete(messages,PLAN_SYSTEM)
    investigation = InvestigationWorkflow(planner,
                                           database, folder/'investigation-workflow')
    return create_app(Agent(model, database, folder / "checkpoints.sqlite"), key, investigation)
