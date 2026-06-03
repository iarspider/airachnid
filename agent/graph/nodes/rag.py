import asyncio

from loguru import logger

from config import agent_settings
from graph.state import AgentState
from rag.retriever import retrieve


async def node_rag(state: AgentState) -> AgentState:
    results, found = await retrieve(state.get("rag_query", ""))
    state["retrieved_docs"] = [_[1] for _ in results]

    state["need_search"] = not found

    logger.info(f"RAG: {found=}, # of results {len(results)}")
    return state
