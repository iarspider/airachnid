from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from config import agent_settings


async def get_checkpointer() -> AsyncRedisSaver:
    """Return a LangGraph RedisSaver checkpointer backed by Redos."""

    checkpointer = AsyncRedisSaver(agent_settings.redis.url)
    await checkpointer.setup()

    return checkpointer
