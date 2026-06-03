import logging
from contextlib import asynccontextmanager

import langfuse
import uvicorn
from fastapi import Body, FastAPI
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from tools.mcp_client import init_mcp_client
from config import agent_settings
from database import async_session_maker
from graph.builder import build_graph
from graph.state import AgentState
from memory.session import make_config
from models.game import Game
from rag.retriever import embed, get_store, init_store
from store import get_checkpointer
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph.state import CompiledStateGraph
from langfuse import get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

checkpointer: AsyncRedisSaver | None = None
graph: CompiledStateGraph | None = None
langfuse_client: langfuse.Langfuse | None = None
# langfuse_handler: CallbackHandler | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global checkpointer, graph, langfuse_client, langfuse_handler

    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
    logging.getLogger("opentelemetry.context").addFilter(OtelFilter())
    await init_store()
    await init_mcp_client()

    langfuse_client = get_client()
    # langfuse_handler = CallbackHandler()

    checkpointer = await get_checkpointer()
    graph = await build_graph(checkpointer=checkpointer)
    yield


app = FastAPI(lifespan=lifespan)


class InvokeRequest(BaseModel):
    request: str
    session: int
    user: int


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /healthz" not in record.getMessage()


class OtelFilter(logging.Filter):
    def filter(self, record):
        return "Failed to detach context" not in record.getMessage()


@app.get("/healthz")
async def healthz():
    return {"status": "OK"}


@app.post("/reindex")
async def reindex():
    store = get_store()

    async with async_session_maker.begin() as sess:
        gog_ids_query = select(Game.gog_id).where(Game.is_hidden == False)
        gog_ids = set(await sess.scalars(gog_ids_query))

        indexed_gog_ids_query = text(
            f"SELECT gog_id FROM {agent_settings.db.table_name}"
        )
        indexed_gog_ids = set(await sess.scalars(indexed_gog_ids_query))

        new_gog_ids = gog_ids - indexed_gog_ids
        games_query = (
            select(Game)
            .where(Game.gog_id.in_(new_gog_ids))
            .options(
                selectinload(Game.genres),
                selectinload(Game.themes),
                selectinload(Game.tags),
                selectinload(Game.collection),
                selectinload(Game.developers),
            )
        )
        games = await sess.scalars(games_query)
        for game in games:
            await embed(game)

    await store.areindex("my-ivfflat")
    await store.areindex("my-hnsw-index")
    return "OK"


@app.post("/invoke")
async def invoke(req: InvokeRequest = Body()):
    # ? config = make_config(req.session, req.user, langfuse_handler)

    state: AgentState = {
        "raw_message": req.request,
        "normalized_message": "",
        "translated_message": "",
        "session_id": str(req.session),
        #
        "intent": "invalid",
        # "messages": [],
        #
        "validation_passed": False,
        #
        "ddg_query": "",
        "rag_query": "",
        "retrieved_docs": [],
        "need_search": False,
        "search_results": [],
        #
        "final_answer": "",
        "success": True,
        "error": "",
        "retry": False,
        "retries": 0,
    }

    print(graph.get_graph().draw_mermaid())
    print("=" * 80)

    with langfuse_client.start_as_current_observation(
        as_type="span",
        name="agent-invoke",
        input={"text": req.request},
    ) as root:
        with propagate_attributes(user_id=str(req.user), session_id=str(req.session)):
            handler = CallbackHandler()

            try:
                result = await graph.ainvoke(
                    state,
                    config={
                        "configurable": {"thread_id": str(req.session)},
                        "callbacks": [handler],
                    },
                )  # type: ignore
                state["final_answer"] = result.get("final_answer", "Нет ответа.")
                root.update(output={"text": state["final_answer"]})
            except Exception as exc:
                logger.opt(exception=exc).error("Внутренняя ошибка агента")
                state["success"] = False
                state["error"] = f"Внутренняя ошибка агента ({type(exc)}: {str(exc)})"
                root.update(output={"error": state["error"]}, level="ERROR")

    if state.get("success", False):
        return {"text": state["final_answer"]}
    else:
        return {"error": state["error"]}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
