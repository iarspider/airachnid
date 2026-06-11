from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from config import agent_settings
from database import async_session_maker
from models.game import Game
from rag.retriever import embed, get_store


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
