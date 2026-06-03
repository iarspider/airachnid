import asyncio
from ddgs import DDGS

from graph.state import AgentState


def do_search(ddgs, query: str) -> list[str]:
    return ddgs.text(query, max_results=5)


async def node_ddg_search(state: AgentState) -> AgentState:
    ddgs = DDGS()
    results = await asyncio.get_running_loop().run_in_executor(
        None, do_search, ddgs, state.get("ddg_query", "")
    )

    return {**state, "search_results": results}
