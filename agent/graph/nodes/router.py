import re

from loguru import logger
from pydantic import BaseModel

from config import agent_settings
from graph.state import AgentState
from llm import invoke_llm
from prompts import RAG_OR_TOOL_PROMPT


class ToolCallResult(BaseModel):
    called: bool
    tool_name: str | None = None
    result: str | None = None


def router_after_validate(state: AgentState) -> str:
    if state.get("validation_passed"):
        return "route_request"
    return "error_handler"


def route_after_route_rag_or_tool(state: AgentState) -> str:
    return state.get("intent", "invalid")


def router_after_validate_output(state: AgentState) -> str:
    if state["success"]:
        return "success"

    if state["retry"] and state["retries"] < agent_settings.graph_max_retries:
        # state["retries"] += 1
        return "retry"

    return "error"


def router_ddg_or_return(state: AgentState) -> str:
    return "ddg" if state.get("need_search") else "generate_output"


def node_rag_or_tool(state: AgentState) -> AgentState:
    res = invoke_llm(
        RAG_OR_TOOL_PROMPT,
        state.get("translated_message", ""),
        model=agent_settings.ollama.classifier_model,
    )

    res = re.sub("[^a-z]", "", res.strip().lower())

    if res not in ("tool", "rag"):
        logger.warning(f"Router returned invalid response: {res}")
        res = "invalid"
        state["success"] = False
        state["error"] = f"Router returned invalid response: {res}"

    logger.info(f"Classified request as {res}")

    return {**state, "intent": res}


def route_after_call_tools(state: AgentState) -> str:
    if state["success"]:
        return "success"

    return "error"
