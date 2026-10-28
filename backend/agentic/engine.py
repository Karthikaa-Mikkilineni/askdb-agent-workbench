"""Model chooses tools; deterministic host enforces permissions and budgets."""
import hashlib
import json
import sqlite3
import threading
import uuid
from typing import Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .policy import PolicyError, validate
from .store import METRICS, TABLES


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["inspect_schema", "metric_definitions", "validate_sql", "explain_sql",
                  "execute_sql", "clarify", "finish"]
    args: dict = Field(default_factory=dict)


class AgentState(TypedDict, total=False):
    messages: list[dict]
    trace: list[dict]
    action: dict
    calls: int
    errors: int
    status: str
    schema: dict
    schema_hash: str
    validated: dict
    result: dict
    clarification: str


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Agent:
    def __init__(self, model, database, checkpoint_path, max_calls=12, max_errors=3):
        self.model, self.database = model, database
        self.max_calls, self.max_errors = max_calls, max_errors
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self.saver = SqliteSaver(self.connection)
        graph = StateGraph(AgentState)
        graph.add_node("decide", self.decide)
        graph.add_node("tool", self.tool)
        graph.add_edge(START, "decide")
        graph.add_conditional_edges("decide", lambda s: "tool" if s["status"] == "running" else END,
                                    {"tool": "tool", END: END})
        graph.add_conditional_edges("tool", lambda s: "decide" if s["status"] == "running" else END,
                                    {"decide": "decide", END: END})
        self.graph = graph.compile(checkpointer=self.saver)

    def close(self):
        self.connection.close()

    def decide(self, state):
        if state["calls"] >= self.max_calls or state["errors"] >= self.max_errors:
            return {"status": "budget_exhausted"}
        if sum(len(m["content"]) for m in state["messages"]) > 24000:
            return {"status": "context_exhausted"}
        try:
            raw = self.model(state["messages"])
            if not isinstance(raw, str) or len(raw) > 12000:
                raise ValueError("Oversized or non-text model response")
            raw = raw.strip()
            # Accept an entire fenced JSON object, never extract JSON from arbitrary prose.
            if raw.endswith("```"):
                for prefix in ("```json\n", "```\n"):
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):-3].strip()
                        break
            action = Action.model_validate_json(raw).model_dump()
            return {"action": action, "calls": state["calls"] + 1}
        except (ValueError, ValidationError, KeyError, TypeError):
            return {"calls": state["calls"] + 1,
                    "status": "running", "action": {"tool": "invalid", "args": {}}}
        except Exception:
            # Fail closed, never return HTTP headers, keys, URLs, or provider body.
            return {"calls": state["calls"] + 1, "status": "model_unavailable"}

    def tool(self, state):
        state = dict(state)
        tool, args = state["action"]["tool"], state["action"]["args"]
        try:
            expected = {"inspect_schema": set(), "metric_definitions": set(), "validate_sql": {"sql"},
                        "explain_sql": set(), "execute_sql": set(), "clarify": {"question"}, "finish": set()}
            sql_reference = tool in {"explain_sql", "execute_sql"} and set(args) == {"sql"}
            if tool not in expected or (set(args) != expected[tool] and not sql_reference):
                raise PolicyError("Invalid action or tool arguments; return the documented JSON action")
            if tool == "inspect_schema":
                state["schema"] = self.database.schema()
                state["schema_hash"] = digest(state["schema"])
                observation = state["schema"]
            elif tool == "metric_definitions":
                observation = METRICS
            elif tool == "validate_sql":
                state["validated"], state["result"] = {}, {}
                if not state.get("schema"):
                    raise PolicyError("Inspect schema before writing SQL")
                sql, sql_hash = validate(args["sql"], TABLES, self.database.dialect)
                token = digest({"sql_hash": sql_hash, "schema": state["schema_hash"]})
                state["validated"] = {"sql": sql, "source_sql": args["sql"], "token": token, "explained": False}
                observation = {"token": token, "sql": sql}
            elif tool in {"explain_sql", "execute_sql"}:
                valid = state.get("validated", {})
                if not valid:
                    raise PolicyError("No matching validated query token")
                if "sql" in args and args["sql"] not in (valid["sql"], valid["source_sql"]):
                    raise PolicyError("SQL reference differs from the validated query")
                if digest(self.database.schema()) != state["schema_hash"]:
                    state["validated"] = {}
                    raise PolicyError("Schema changed; inspect and validate again")
                if tool == "explain_sql":
                    observation = self.database.explain(valid["sql"])
                    state["validated"] = {**valid, "explained": True}
                else:
                    if not valid["explained"]:
                        raise PolicyError("Run explain_sql successfully before execution")
                    observation = self.database.execute(valid["sql"])
                    state["result"] = {**observation, "sql": valid["sql"], "evidence_hash": digest(observation)}
                    # This service returns execution evidence, not an LLM-written answer.
                    # Successful execution fulfills this single-query job; no redundant finish call.
                    state["status"] = "completed"
            elif tool == "clarify":
                q = args["question"]
                if not isinstance(q, str) or not 1 <= len(q) <= 500:
                    raise PolicyError("Clarification must contain 1 to 500 characters")
                state["status"], state["clarification"] = "needs_clarification", q
                observation = {"question": q}
            else:
                if not state.get("result"):
                    raise PolicyError("No execution evidence; cannot finish")
                state["status"] = "completed"
                observation = {"evidence_hash": state["result"]["evidence_hash"]}
            event = {"tool": tool, "args": args, "ok": True, "observation": observation}
        except (PolicyError, sqlite3.Error, ValueError) as exc:
            # Controlled policy text / SQLite syntax diagnostics on synthetic local data.
            state["errors"] += 1
            state["result"] = {}
            event = {"tool": tool, "args": args, "ok": False, "error": str(exc)[:250]}
        except Exception as exc:
            state["errors"] += 1
            # PostgreSQL undefined-column / undefined-table feedback contains only SQLSTATE.
            code = getattr(exc, "pgcode", None)
            event = {"tool": tool, "args": args, "ok": False,
                     "error": "Database operation failed" + (f" (SQLSTATE {code})" if code else ""),
                     "error_type": type(exc).__name__}
        state["trace"] = [*state["trace"], event]
        state["messages"] = [*state["messages"],
                             {"role": "assistant", "content": json.dumps(state["action"])},
                             {"role": "user", "content": "UNTRUSTED TOOL OBSERVATION: " + json.dumps(event, default=str)}]
        return state

    def run(self, question, thread_id=None):
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
            raise ValueError("Question must contain 1 to 2000 characters")
        thread_id = thread_id or str(uuid.uuid4())
        # Server API parses UUID as well. No filesystem paths are derived from this value.
        uuid.UUID(thread_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
        with self.lock:
            previous = self.graph.get_state(config).values
            history = previous.get("messages", [])
            # Preserve context only for a pending clarification; completed jobs start fresh.
            if previous.get("status") != "needs_clarification":
                history = []
            state = self.graph.invoke({"messages": [*history, {"role": "user", "content": question}],
                                      "trace": [], "calls": 0, "errors": 0, "status": "running",
                                      "schema": {}, "schema_hash": "", "validated": {}, "result": {},
                                      "clarification": ""}, config)
        return {"thread_id": thread_id, **{key: state.get(key) for key in
                ["status", "calls", "errors", "trace", "result", "clarification"]}}
