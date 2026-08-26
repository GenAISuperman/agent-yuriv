"""
PLATFORM: Agent entry point — LangGraph agent with FastAPI endpoints.

This file implements:
  POST /invoke   — OpenAI chat completions API format
  POST /evaluate — internal endpoint for Promptfoo eval
  GET  /health   — AKS liveness and readiness probes

Add your business logic in agent_node(). The SDK handles auth, headers,
OTel context propagation, and APIM routing. Never call backends directly.
"""

from __future__ import annotations

import os
import time
from typing import Any, TypedDict
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from pydantic import BaseModel

from agent_platform_sdk import AgentContext
from src.prompts import load_prompt

load_dotenv()

# ---------------------------------------------------------------------------
# OpenTelemetry setup
# ---------------------------------------------------------------------------
_tracer_provider = TracerProvider()
_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if _otlp_endpoint:
    _tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=_otlp_endpoint))
    )
trace.set_tracer_provider(_tracer_provider)
tracer = trace.get_tracer(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
AGENT_ID: str = os.getenv("AGENT_ID", "unknown-agent")
TEAM_NAME: str = os.getenv("TEAM_NAME", "unknown-team")
PROMPT_VERSION: str = "v1.0"

# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: list[dict[str, str]]
    session_id: str
    correlation_id: str
    user_token: str | None


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------
def agent_node(state: AgentState) -> AgentState:
    """Core agent logic. Add your tool calls and business logic here."""

    # PLATFORM: LLM is initialised per-request so the app starts without
    # Azure credentials (required for /health to work on its own).
    llm = AzureChatOpenAI(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        azure_ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version="2024-02-01",
    )

    system_prompt = load_prompt()
    langchain_messages: list[Any] = [SystemMessage(content=system_prompt)]

    for msg in state["messages"]:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))

    # PLATFORM: Build agent context for SDK tool calls
    agent_context = AgentContext(
        agent_id=os.getenv("AGENT_ID", ""),
        team=os.getenv("TEAM_NAME", ""),
        correlation_id=state["correlation_id"],
        user_token=state.get("user_token"),
        platform_registry_url=os.getenv("PLATFORM_REGISTRY_URL", ""),
    )

    # PLATFORM: Add your tool calls here using get_tool()
    # PLATFORM: The SDK handles auth, headers, OTel, APIM routing
    # PLATFORM: Never call backends directly from agent code
    # PLATFORM: Example:
    #   from agent_platform_sdk import get_tool
    #   products = get_tool("products-api", context=agent_context)
    #   results = products.list(category="jackets")

    _ = agent_context  # noqa: F841 — used by tool calls above

    response: AIMessage = llm.invoke(langchain_messages)

    state["messages"].append({"role": "assistant", "content": str(response.content)})
    return state


# ---------------------------------------------------------------------------
# LangGraph graph
# ---------------------------------------------------------------------------
_graph_builder = StateGraph(AgentState)
_graph_builder.add_node("agent", agent_node)
_graph_builder.set_entry_point("agent")
_graph_builder.add_edge("agent", END)
graph = _graph_builder.compile()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title=f"Agent: {AGENT_ID}", version="1.0.0")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class InvokeRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    stream: bool = False


class EvaluateRequest(BaseModel):
    prompt_text: str
    prompt_version_label: str
    dataset_id: str
    run_label: str
    messages: list[ChatMessage]


# ---------------------------------------------------------------------------
# POST /invoke — OpenAI chat completions API format
# ---------------------------------------------------------------------------
@app.post("/invoke")
async def invoke(request: Request, body: InvokeRequest) -> JSONResponse:
    session_id: str = request.headers.get("X-Session-ID", str(uuid4()))
    correlation_id: str = request.headers.get("X-Correlation-ID", str(uuid4()))
    user_token: str | None = request.headers.get("X-User-Token")

    with tracer.start_as_current_span("agent.invoke") as span:
        span.set_attribute("agent.id", AGENT_ID)
        span.set_attribute("agent.team", TEAM_NAME)
        span.set_attribute("prompt.version", PROMPT_VERSION)
        span.set_attribute("session.id", session_id)
        span.set_attribute("correlation.id", correlation_id)

        initial_state: AgentState = {
            "messages": [m.model_dump() for m in body.messages],
            "session_id": session_id,
            "correlation_id": correlation_id,
            "user_token": user_token,
        }

        result = graph.invoke(initial_state)
        assistant_content: str = result["messages"][-1]["content"]

        # PLATFORM: Token counts are approximate — replace with real counts
        # when the LLM provider returns usage metadata.
        prompt_tokens = sum(len(m.content.split()) for m in body.messages)
        completion_tokens = len(assistant_content.split())

        response_body = {
            "id": f"chatcmpl-{uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": AGENT_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

        return JSONResponse(
            content=response_body,
            headers={
                "X-Session-ID": session_id,
                "X-Correlation-ID": correlation_id,
            },
        )


# ---------------------------------------------------------------------------
# POST /evaluate — internal, called by Promptfoo (restricted by APIM)
# ---------------------------------------------------------------------------
@app.post("/evaluate")
async def evaluate(body: EvaluateRequest) -> JSONResponse:
    system_prompt = load_prompt(override_text=body.prompt_text)

    messages_for_state: list[dict[str, str]] = [
        m.model_dump() for m in body.messages
    ]

    state: AgentState = {
        "messages": messages_for_state,
        "session_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "user_token": None,
    }

    # PLATFORM: Override system prompt for eval — the load_prompt override
    # ensures the eval-specific prompt is used instead of the file.
    result = graph.invoke(state)
    assistant_content: str = result["messages"][-1]["content"]

    return JSONResponse(
        content={
            "run_id": str(uuid4()),
            "output": assistant_content,
            "prompt_version": body.prompt_version_label,
            "status": "completed",
        }
    )


# ---------------------------------------------------------------------------
# GET /health — no auth, used by AKS liveness/readiness probes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "agent_id": AGENT_ID,
        "prompt_version": PROMPT_VERSION,
    }
