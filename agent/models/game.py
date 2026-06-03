import datetime
import enum
from typing import Annotated

from sqlalchemy import BigInteger, Column, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

created_at_type = Annotated[
    datetime.datetime,
    mapped_column(nullable=False, server_default=func.now()),
]

updated_at_type = Annotated[
    datetime.datetime,
    mapped_column(nullable=False, server_default=func.now(), onupdate=func.now()),
]


class Platform(enum.Enum):
    STEAM = "steam"
    GOG = "gog"
    EPIC = "epic"
    GENERIC = "generic"


game_genres = Table(
    "game_genres",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id"), primary_key=True),
)

game_publishers = Table(
    "game_publishers",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("publisher_id", ForeignKey("publishers.id"), primary_key=True),
)

game_developers = Table(
    "game_developers",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("developer_id", ForeignKey("developers.id"), primary_key=True),
)

game_themes = Table(
    "game_themes",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("theme_id", ForeignKey("themes.id"), primary_key=True),
)

game_tags = Table(
    "game_tags",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)

game_collections = Table(
    "game_collections",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("collection_id", ForeignKey("collections.id"), primary_key=True),
)

game_platforms = Table(
    "game_platforms",
    Base.metadata,
    Column("game_id", BigInteger, ForeignKey("games.gog_id"), primary_key=True),
    Column("platform", String, primary_key=True, nullable=False),
)


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    games: Mapped[list["Game"]] = relationship(
        secondary=game_genres, back_populates="genres"
    )


class Publisher(Base):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    games: Mapped[list["Game"]] = relationship(
        secondary=game_publishers, back_populates="publishers"
    )


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    games: Mapped[list["Game"]] = relationship(
        secondary=game_developers, back_populates="developers"
    )


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    games: Mapped[list["Game"]] = relationship(
        secondary=game_themes, back_populates="themes"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    games: Mapped[list["Game"]] = relationship(
        secondary=game_tags, back_populates="tags"
    )


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    igdb_id: Mapped[int | None] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(unique=True)

    games: Mapped[list["Game"]] = relationship(
        secondary=game_collections, back_populates="collection"
    )


class Game(Base):
    __tablename__ = "games"

    gog_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    igdb_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    twitch_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    title: Mapped[str]
    sorting_title: Mapped[str | None]
    summary: Mapped[str | None]
    critics_score: Mapped[str | None]
    release_date: Mapped[datetime.datetime | None]
    is_hidden: Mapped[bool] = mapped_column(default=False)
    background_image: Mapped[str | None]
    square_icon: Mapped[str | None]
    vertical_cover: Mapped[str | None]
    cover_path: Mapped[str | None]
    created_at: Mapped[created_at_type]
    updated_at: Mapped[updated_at_type]
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id"))
    collection_order: Mapped[int | None]
    collection_sort_key: Mapped[str | None]

    genres: Mapped[list[Genre]] = relationship(
        secondary=game_genres, back_populates="games"
    )
    publishers: Mapped[list[Publisher]] = relationship(
        secondary=game_publishers, back_populates="games"
    )
    developers: Mapped[list[Developer]] = relationship(
        secondary=game_developers, back_populates="games"
    )
    themes: Mapped[list[Theme]] = relationship(
        secondary=game_themes, back_populates="games"
    )
    tags: Mapped[list[Tag]] = relationship(secondary=game_tags, back_populates="games")
    collection: Mapped[Collection | None] = relationship(back_populates="games")


class GameSearchTitle(Base):
    __tablename__ = "game_search_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("games.gog_id"))
    token: Mapped[str]


class IGDBCandidate(Base):
    __tablename__ = "igdb_candidate"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("games.gog_id"))
    igdb_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str]
    year: Mapped[int]
    cover_url: Mapped[str | None] = None
