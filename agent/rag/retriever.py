import numpy as np
from langchain_core.documents import Document
from langchain_postgres import Column, PGEngine, PGVectorStore
from langchain_postgres.v2.indexes import HNSWIndex, IVFFlatIndex
from loguru import logger
from sqlalchemy import inspect, text

from config import agent_settings
from database import async_session_maker
from models.game import Game
from rag.embedder import get_embedding_service

from psycopg.sql import SQL, Identifier

_store: PGVectorStore | None = None


def check_vector_store(conn) -> bool:
    inspector = inspect(conn)
    if not inspector:
        raise RuntimeError("Failed to create inspector!")

    return inspector.has_table(agent_settings.db.table_name)


async def init_store() -> None:
    global _store
    #
    # has_vector_store: bool = False
    #
    engine = PGEngine.from_connection_string(agent_settings.db.url)
    #
    # async with engine._pool.connect() as conn:
    #     has_vector_store = await conn.run_sync(
    #         lambda sync_conn: check_vector_store(sync_conn)
    #     )
    #
    # if not has_vector_store:
    #     logger.info(f"Creating vectorstore table {agent_settings.db.table_name}")
    #     await engine.ainit_vectorstore_table(
    #         table_name=agent_settings.db.table_name,
    #         vector_size=agent_settings.db.vector_size,
    #         id_column=Column(name="gog_id", data_type="BIGINT"),
    #     )
    #
    _store = await PGVectorStore.create(
        engine=engine,
        table_name=agent_settings.db.table_name,
        embedding_service=get_embedding_service(),
        id_column="gog_id",
    )
    #
    # if not has_vector_store:
    #     index = IVFFlatIndex(name="my-ivfflat", lists=120)
    #     _store.apply_vector_index(index)
    #
    #     index = HNSWIndex(name="my-hnsw-index")
    #     _store.apply_vector_index(index)
    #
    # async with engine._pool.connect() as conn:
    #     await conn.execute(SQL("""
    #             ALTER TABLE {table}
    #                 ADD COLUMN IF NOT EXISTS fts tsvector
    #                 GENERATED ALWAYS AS (
    #                 to_tsvector('english', coalesce (content, ''))
    #                 ) STORED
    #             """).format(table=Identifier(agent_settings.db.table_name)))
    #
    #     # Create GIN index for FTS
    #     await conn.execute(
    #         SQL("""
    #             CREATE INDEX IF NOT EXISTS {index_name}
    #                 ON {table}
    #                 USING GIN (fts)
    #             """).format(
    #             index_name=Identifier(f"{agent_settings.db.table_name}_fts_idx"),
    #             table=Identifier(agent_settings.db.table_name),
    #         )
    #     )
    #
    #     await conn.commit()


async def semantic_search(query: str, k=5) -> list[tuple]:
    store = get_store()
    docs = await store.asimilarity_search_with_score(query, k)
    #
    # THRESHOLD = 0.5
    # good = [
    #     doc.page_content for doc, score in docs if score < THRESHOLD
    # ]  # score: less is better

    logger.info(
        f"Found {len(docs)} documents"  # ", of which {len(good)} had score less than {THRESHOLD}"
    )

    for i, d in enumerate(docs, 1):
        logger.debug(f'Document #{i}: score {d[1]}, title {d[0].metadata["title"]}')

    # found = len(good) > 0

    # return good, found
    return docs


async def keyword_search(text_, k=10):  # top-k BM25
    async with async_session_maker.begin() as sess:
        query = text(f"""SELECT gog_id, content, 
                       ts_rank_cd(fts, plainto_tsquery('english', :text)) AS bm25
                       FROM {agent_settings.db.table_name}
                       WHERE fts @@ plainto_tsquery('english', :text)
                       ORDER BY bm25 DESC LIMIT :limit
""")
        result = await sess.execute(query, {"text": text_, "limit": k})
        return result.fetchall()


async def retrieve(query: str, k: int = 5) -> tuple[list[tuple[float, str]], bool]:
    v_hits = await semantic_search(query, k=20)
    b_hits = await keyword_search(query, k=20)

    best_semantic_score = v_hits[0][1] if v_hits else 1.0
    confident = best_semantic_score < agent_settings.search_threshold

    RRF_K = 60
    combined: dict[str, dict] = {}

    for rank, (doc, _score) in enumerate(v_hits):
        gog_id = str(doc.metadata["gog_id"])
        combined.setdefault(gog_id, {"content": doc.page_content, "v": 0.0, "b": 0.0})
        combined[gog_id]["v"] += 1 / (RRF_K + rank)

    for rank, (gog_id, content, _bm25) in enumerate(b_hits):
        gog_id = str(gog_id)
        combined.setdefault(gog_id, {"content": content, "v": 0.0, "b": 0.0})
        combined[gog_id]["b"] += 1 / (RRF_K + rank)

    alpha = agent_settings.search_alpha  # 0.5 по умолчанию
    scored = [
        (alpha * v["v"] + (1 - alpha) * v["b"], v["content"]) for v in combined.values()
    ]

    scored.sort(key=lambda x: x[0], reverse=True)

    logger.debug(f"RRF results (top {k}):")
    for score, content in scored[:k]:
        title = content.split("\n")[0]  # первая строка — "Название: X"
        logger.debug(f"  score={score:.4f} {title}")

    return scored[:k], confident


def game_to_document(game: Game) -> str:
    parts = [f"Title: {game.title}"]

    if game.genres:
        genres = ", ".join(g.name for g in game.genres)
        parts.append(f"Genres: {genres}")

    if game.themes:
        themes = ", ".join(t.name for t in game.themes)
        parts.append(f"Themes: {themes}")

    if game.tags:
        tags = ", ".join(t.name for t in game.tags)
        parts.append(f"Tags: {tags}")

    if game.developers:
        devs = ", ".join(d.name for d in game.developers)
        parts.append(f"Developers: {devs}")

    if game.collection:
        parts.append(f"Series: {game.collection.name}")

    if game.release_date:
        parts.append(f"Year: {game.release_date.year}")

    if game.summary:
        summary = game.summary[:300]
        parts.append(f"Description: {summary}")

    return "\n".join(parts)


async def embed(g: Game):
    store = get_store()

    content = game_to_document(g)
    docs = [
        Document(
            id=g.gog_id,
            page_content=content,
            metadata={"gog_id": str(g.gog_id), "title": g.title},
        )
    ]

    await store.aadd_documents(docs)


def get_store() -> PGVectorStore:
    if not _store:
        raise RuntimeError("Store not initialized, call init_store() first")

    return _store
