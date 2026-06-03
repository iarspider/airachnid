CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
CREATE TABLE collections (
	id INTEGER NOT NULL, 
	igdb_id BIGINT, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (igdb_id), 
	UNIQUE (name)
);
CREATE TABLE developers (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE genres (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE publishers (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE tags (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE themes (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);
CREATE TABLE games (
	gog_id BIGINT NOT NULL, 
	igdb_id BIGINT, 
	twitch_id BIGINT, 
	title VARCHAR NOT NULL, 
	sorting_title VARCHAR, 
	summary VARCHAR, 
	critics_score VARCHAR, 
	release_date TIMESTAMP, 
	is_hidden BOOLEAN NOT NULL, 
	background_image VARCHAR, 
	square_icon VARCHAR, 
	vertical_cover VARCHAR, 
	cover_path VARCHAR, 
	created_at TIMESTAMP DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP DEFAULT now() NOT NULL, 
	collection_id INTEGER, 
	collection_order INTEGER, 
	collection_sort_key VARCHAR, 
	PRIMARY KEY (gog_id), 
	FOREIGN KEY(collection_id) REFERENCES collections (id), 
	UNIQUE (igdb_id), 
	UNIQUE (twitch_id)
);
CREATE TABLE game_collections (
	game_id BIGINT NOT NULL, 
	collection_id INTEGER NOT NULL, 
	PRIMARY KEY (game_id, collection_id), 
	FOREIGN KEY(collection_id) REFERENCES collections (id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id)
);
CREATE TABLE game_developers (
	game_id BIGINT NOT NULL, 
	developer_id INTEGER NOT NULL, 
	PRIMARY KEY (game_id, developer_id), 
	FOREIGN KEY(developer_id) REFERENCES developers (id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id)
);
CREATE TABLE game_genres (
	game_id BIGINT NOT NULL, 
	genre_id INTEGER NOT NULL, 
	PRIMARY KEY (game_id, genre_id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id), 
	FOREIGN KEY(genre_id) REFERENCES genres (id)
);
CREATE TABLE game_platforms (
	game_id BIGINT NOT NULL, 
	platform VARCHAR NOT NULL, 
	PRIMARY KEY (game_id, platform), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id)
);
CREATE TABLE game_publishers (
	game_id BIGINT NOT NULL, 
	publisher_id INTEGER NOT NULL, 
	PRIMARY KEY (game_id, publisher_id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id), 
	FOREIGN KEY(publisher_id) REFERENCES publishers (id)
);
CREATE TABLE game_tags (
	game_id BIGINT NOT NULL, 
	tag_id INTEGER NOT NULL, 
	PRIMARY KEY (game_id, tag_id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id), 
	FOREIGN KEY(tag_id) REFERENCES tags (id)
);
CREATE TABLE game_themes (
	game_id BIGINT NOT NULL, 
	theme_id INTEGER NOT NULL, 
	PRIMARY KEY (game_id, theme_id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id), 
	FOREIGN KEY(theme_id) REFERENCES themes (id)
);
CREATE TABLE game_search_tokens (
	id INTEGER NOT NULL, 
	game_id BIGINT NOT NULL, 
	token VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id)
);
CREATE TABLE igdb_candidate (
	id INTEGER NOT NULL, 
	game_id BIGINT NOT NULL, 
	igdb_id BIGINT NOT NULL, 
	title VARCHAR NOT NULL, 
	year INTEGER NOT NULL, 
	cover_url VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(game_id) REFERENCES games (gog_id)
);
