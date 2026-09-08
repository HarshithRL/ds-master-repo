-- W0 KB foundation (Lakebase / Postgres). Do not run against sqlite.
-- BLOCKED in local/dev until Lakebase credentials are available.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunk_embedding (
  chunk_id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  vendor_id VARCHAR,
  doc_role VARCHAR,
  chunk_type VARCHAR,
  embedding vector(1024) NOT NULL,
  model_version VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw
  ON chunk_embedding USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_chunk_embedding_filter
  ON chunk_embedding (project_id, vendor_id, doc_role, chunk_type);

-- Generated tsvector: skip if column already exists.
ALTER TABLE chunk ADD COLUMN IF NOT EXISTS tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('english', text)) STORED;
CREATE INDEX IF NOT EXISTS ix_chunk_tsv ON chunk USING gin (tsv);
