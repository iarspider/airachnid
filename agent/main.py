import logging
from contextlib import asynccontextmanager

import langfuse
import uvicorn
from fastapi import Body, FastAPI
from langfuse import get_client
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from pydantic import BaseModel

from data_plane.executor import run_agent
from data_plane.store import reindex as do_reindex
from graph.builder import build_graph
from rag.retriever import init_store
from store import get_checkpointer
from tools.mcp_client import init_mcp_client

checkpointer: AsyncRedisSaver | None = None
graph: CompiledStateGraph | None = None
langfuse_client: langfuse.Langfuse | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global checkpointer, graph, langfuse_client

    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
    logging.getLogger("opentelemetry.context").addFilter(OtelFilter())
    await init_store()
    await init_mcp_client()

    langfuse_client = get_client()

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
    try:
        await do_reindex()
    except Exception as e:
        logger.opt(exception=e).exception("Exception during reindex!")
        return {"status": "ERROR"}
    else:
        return {"status": "OK"}


@app.post("/invoke")
async def invoke(req: InvokeRequest = Body()):
    return run_agent(req.request, req.user, req.session, graph, langfuse_client)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
