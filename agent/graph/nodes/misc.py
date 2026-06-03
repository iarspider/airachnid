from graph.state import AgentState
from llm import invoke_llm
from prompts import TOOL_RESULT_PROMPT


def node_error_handler(state: AgentState) -> AgentState:
    state["final_answer"] = state.get("error", "Неизвестная ошибка")
    state["success"] = False
    return state


def node_increment_retry(state: AgentState) -> AgentState:
    return {**state, "retries": state.get("retries", 0) + 1, "retry": False}
