from typing import List, Literal, Required, TypedDict

from langchain_core.messages import BaseMessage

Intent = Literal["rag", "tool", "invalid"]
# ToolIntent = Literal["vlc", "wiz", "invalid"]


class AgentState(TypedDict, total=False):
    raw_message: Required[str]
    normalized_message: str
    translated_message: str
    session_id: Required[str]

    intent: Intent
    messages: list[BaseMessage]

    validation_passed: bool

    validation_score: float
    validation_relevance: float
    validation_completeness: float

    ddg_query: str
    rag_query: str
    retrieved_docs: List[str]
    need_search: bool
    search_results: list[str]

    final_answer: Required[str]
    success: bool
    error: str

    retries: int
    retry: bool
