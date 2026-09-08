-- W0 KB foundation (sqlite). Additive only.
-- Applied by shared.db.migrate.apply_kb_foundation. Idempotent.

-- identity + provenance on artifacts
-- ALTER TABLE artifact ADD COLUMN vendor_id VARCHAR;
-- ALTER TABLE artifact ADD COLUMN doc_role VARCHAR;
-- ALTER TABLE artifact ADD COLUMN role_confidence REAL;
-- ALTER TABLE artifact ADD COLUMN content_hash VARCHAR;
-- ALTER TABLE artifact ADD COLUMN superseded_by VARCHAR;
-- ALTER TABLE chunk ADD COLUMN table_json TEXT;
-- ALTER TABLE chunk ADD COLUMN page_kind VARCHAR;
-- ALTER TABLE chunk ADD COLUMN reconstructor VARCHAR;
-- UPDATE artifact SET parse_status='pending' WHERE parse_status IS NULL;

CREATE TABLE IF NOT EXISTS vendor (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  legal_entity VARCHAR,
  registry_id VARCHAR,
  status VARCHAR DEFAULT 'bidder',
  created_at VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  ordinal INTEGER NOT NULL,
  section VARCHAR,
  text TEXT NOT NULL,
  category VARCHAR,
  weight REAL,
  mandatory INTEGER NOT NULL DEFAULT 0,
  source_artifact_id VARCHAR,
  source_page INTEGER,
  created_at VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  requirement_id VARCHAR NOT NULL,
  vendor_id VARCHAR NOT NULL,
  status VARCHAR NOT NULL CHECK (status IN (
    'met','partial','not_offered','not_stated','unclear','extraction_failed'
  )),
  claim_text TEXT,
  artifact_id VARCHAR,
  chunk_id VARCHAR,
  page INTEGER,
  confidence REAL,
  model_version VARCHAR NOT NULL,
  prompt_version VARCHAR NOT NULL,
  extracted_at VARCHAR NOT NULL,
  reviewed_by VARCHAR,
  reviewed_at VARCHAR,
  UNIQUE (requirement_id, vendor_id, model_version)
);

CREATE TABLE IF NOT EXISTS pricing_line (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR,
  vendor_id VARCHAR,
  offer_type VARCHAR NOT NULL CHECK (offer_type IN ('fixed_price','time_and_materials')),
  role VARCHAR,
  seniority VARCHAR,
  rate NUMERIC,
  rate_unit VARCHAR,
  currency VARCHAR,
  quantity NUMERIC,
  line_total NUMERIC,
  etex_effort_days NUMERIC,
  etex_effort_side VARCHAR,
  discount_terms TEXT,
  annexe_a02_completed INTEGER,
  artifact_id VARCHAR,
  page INTEGER,
  chunk_id VARCHAR,
  verified INTEGER NOT NULL DEFAULT 0,
  model_version VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS bid_profile (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  vendor_id VARCHAR NOT NULL,
  facts_json TEXT NOT NULL,
  model_version VARCHAR NOT NULL,
  extracted_at VARCHAR NOT NULL,
  UNIQUE (project_id, vendor_id, model_version)
);

CREATE TABLE IF NOT EXISTS kb_node (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  type VARCHAR NOT NULL CHECK (type IN (
    'LegalEntity','Bid','Person','Requirement','Control','Evidence','Artifact','PricingOffer','Scope'
  )),
  label VARCHAR NOT NULL,
  props TEXT,
  source_artifact_id VARCHAR,
  source_page INTEGER,
  confidence REAL,
  model_version VARCHAR
);

CREATE TABLE IF NOT EXISTS kb_edge (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  src VARCHAR NOT NULL REFERENCES kb_node(id),
  dst VARCHAR NOT NULL REFERENCES kb_node(id),
  type VARCHAR NOT NULL CHECK (type IN (
    'BIDS_ON','MEMBER_OF_CONSORTIUM','PARENT_OF','EMPLOYS','ASSIGNED_ROLE',
    'SUBCONTRACTS_TO','RESPONDS_TO','CITES','IN_SCOPE_FOR','SUPERSEDES','CONFLICTS_WITH'
  )),
  props TEXT,
  source_artifact_id VARCHAR,
  source_page INTEGER,
  confidence REAL,
  model_version VARCHAR
);

CREATE INDEX IF NOT EXISTS ix_edge_src ON kb_edge(project_id, src, type);
CREATE INDEX IF NOT EXISTS ix_edge_dst ON kb_edge(project_id, dst, type);

CREATE TABLE IF NOT EXISTS quality_flag (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR,
  artifact_id VARCHAR,
  kind VARCHAR NOT NULL,
  detail TEXT,
  severity VARCHAR,
  created_at VARCHAR NOT NULL
);
