CREATE TABLE public.game_embeddings (
    gog_id int8 NOT NULL,
    content text NOT NULL,
    embedding public.vector(1024) NOT NULL,
    langchain_metadata json NULL,
    fts tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED,
    CONSTRAINT game_embeddings_pkey PRIMARY KEY (gog_id)
);

CREATE INDEX "my-hnsw-index" ON public.game_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m='16', ef_construction='64');

CREATE INDEX "my-ivfflat" ON public.game_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists='120');

CREATE INDEX "game_embeddings_fts_idx" ON public.game_embeddings
    USING GIN(fts);
