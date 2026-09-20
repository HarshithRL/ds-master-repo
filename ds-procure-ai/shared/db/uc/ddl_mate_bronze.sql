-- Mate Unity Catalog bronze DDL (Delta)
-- Replace {catalog} with automation_d | automation_a | automation_p (from MATE_UC_CATALOG / var.catalog).
-- Schema: bronze. Table prefix: mate_
-- Timestamps stored as STRING ISO-8601 to match SQLite/SQLAlchemy models.
-- Do NOT drop Lakebase mate_agent (LangGraph checkpoints) — that is separate Postgres.
--
-- Example:
--   USE CATALOG automation_d;
--   USE SCHEMA bronze;
--   -- then run statements below with {catalog} substituted, or run FQNs as written.

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_hub_module (
  id STRING,
  name STRING NOT NULL,
  description STRING,
  icon STRING,
  path STRING NOT NULL,
  category STRING NOT NULL,
  sort_order BIGINT NOT NULL,
  enabled BIGINT NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_app_user (
  workspace_id STRING,
  user_name STRING,
  display_name STRING,
  email STRING,
  created_at STRING NOT NULL,
  updated_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_user_module (
  workspace_id STRING NOT NULL,
  module_id STRING NOT NULL,
  granted_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_project (
  id STRING,
  code STRING NOT NULL,
  owner_id STRING NOT NULL,
  module_id STRING NOT NULL,
  name STRING NOT NULL,
  workflow_entry_point STRING,
  business_process STRING,
  requester STRING,
  dept STRING,
  category STRING,
  region STRING,
  status STRING NOT NULL,
  priority STRING NOT NULL,
  budget STRING,
  award_horizon STRING,
  description STRING,
  progress BIGINT NOT NULL,
  deadline STRING,
  requirements_json STRING,
  created_at STRING NOT NULL,
  updated_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_artifact (
  id STRING,
  project_id STRING NOT NULL,
  uploaded_by STRING NOT NULL,
  kind STRING NOT NULL,
  folder STRING,
  original_name STRING NOT NULL,
  content_type STRING,
  size_bytes BIGINT,
  storage_relpath STRING NOT NULL,
  parsed_json STRING,
  parse_status STRING,
  parse_error STRING,
  parsed_relpath STRING,
  vendor_id STRING,
  doc_role STRING,
  role_confidence DOUBLE,
  content_hash STRING,
  superseded_by STRING,
  created_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_chunk (
  id STRING,
  project_id STRING NOT NULL,
  artifact_id STRING NOT NULL,
  ordinal BIGINT NOT NULL,
  chunk_type STRING NOT NULL,
  text STRING NOT NULL,
  token_count BIGINT NOT NULL,
  heading_path_json STRING,
  block_ids_json STRING,
  location_json STRING,
  table_json STRING,
  page_kind STRING,
  reconstructor STRING,
  created_at STRING NOT NULL
) USING DELTA;

-- Embeddings: ARRAY<DOUBLE> stands in for pgvector(1024) from Lakebase migration.
CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_chunk_embedding (
  chunk_id STRING,
  project_id STRING NOT NULL,
  vendor_id STRING,
  doc_role STRING,
  chunk_type STRING,
  embedding ARRAY<DOUBLE> NOT NULL,
  model_version STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_vendor (
  id STRING,
  project_id STRING NOT NULL,
  name STRING NOT NULL,
  legal_entity STRING,
  registry_id STRING,
  status STRING,
  created_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_requirement (
  id STRING,
  project_id STRING NOT NULL,
  ordinal BIGINT NOT NULL,
  section STRING,
  text STRING NOT NULL,
  category STRING,
  weight DOUBLE,
  mandatory BIGINT NOT NULL,
  source_artifact_id STRING,
  source_page BIGINT,
  created_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_evidence (
  id STRING,
  project_id STRING NOT NULL,
  requirement_id STRING NOT NULL,
  vendor_id STRING NOT NULL,
  status STRING NOT NULL,
  claim_text STRING,
  artifact_id STRING,
  chunk_id STRING,
  page BIGINT,
  confidence DOUBLE,
  model_version STRING NOT NULL,
  prompt_version STRING NOT NULL,
  extracted_at STRING NOT NULL,
  reviewed_by STRING,
  reviewed_at STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_pricing_line (
  id STRING,
  project_id STRING,
  vendor_id STRING,
  offer_type STRING NOT NULL,
  role STRING,
  seniority STRING,
  rate DOUBLE,
  rate_unit STRING,
  currency STRING,
  quantity DOUBLE,
  line_total DOUBLE,
  etex_effort_days DOUBLE,
  etex_effort_side STRING,
  discount_terms STRING,
  annexe_a02_completed BIGINT,
  artifact_id STRING,
  page BIGINT,
  chunk_id STRING,
  verified BIGINT NOT NULL,
  model_version STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_bid_profile (
  id STRING,
  project_id STRING NOT NULL,
  vendor_id STRING NOT NULL,
  facts_json STRING NOT NULL,
  model_version STRING NOT NULL,
  extracted_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_kb_node (
  id STRING,
  project_id STRING NOT NULL,
  type STRING NOT NULL,
  label STRING NOT NULL,
  props STRING,
  source_artifact_id STRING,
  source_page BIGINT,
  confidence DOUBLE,
  model_version STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_kb_edge (
  id STRING,
  project_id STRING NOT NULL,
  src STRING NOT NULL,
  dst STRING NOT NULL,
  type STRING NOT NULL,
  props STRING,
  source_artifact_id STRING,
  source_page BIGINT,
  confidence DOUBLE,
  model_version STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_chat_session (
  id STRING,
  project_id STRING NOT NULL,
  title STRING NOT NULL,
  created_at STRING NOT NULL,
  updated_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_chat_message (
  id STRING,
  session_id STRING NOT NULL,
  role STRING NOT NULL,
  text STRING NOT NULL,
  created_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_ontology_requirement (
  id STRING,
  project_id STRING NOT NULL,
  req_id STRING NOT NULL,
  text STRING NOT NULL,
  category STRING NOT NULL,
  target STRING,
  mandatory BIGINT NOT NULL,
  weight DOUBLE,
  ontology_version STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_ontology_offering (
  id STRING,
  project_id STRING NOT NULL,
  vendor_id STRING NOT NULL,
  req_id STRING NOT NULL,
  status STRING NOT NULL,
  value_text STRING NOT NULL,
  numeric_value DOUBLE,
  locator STRING NOT NULL,
  quote STRING NOT NULL,
  chunk_id STRING,
  confidence DOUBLE
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_tco_line (
  id STRING,
  project_id STRING NOT NULL,
  vendor_id STRING NOT NULL,
  year BIGINT NOT NULL,
  line_type STRING NOT NULL,
  amount_eur DOUBLE,
  mandays DOUBLE,
  rate_eur_per_day DOUBLE,
  derived BIGINT NOT NULL,
  locator STRING NOT NULL,
  note STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_ontology_flag (
  id STRING,
  project_id STRING NOT NULL,
  severity STRING NOT NULL,
  text STRING NOT NULL,
  vendors_json STRING NOT NULL,
  locator STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_pack (
  id STRING,
  project_id STRING NOT NULL,
  kind STRING NOT NULL,
  status STRING NOT NULL,
  path STRING,
  created_at STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_quality_flag (
  id STRING,
  project_id STRING,
  artifact_id STRING,
  kind STRING NOT NULL,
  detail STRING,
  severity STRING,
  created_at STRING NOT NULL
) USING DELTA;

-- Analyst decision log. bid_id NULL = project-level note.
CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_note (
  id STRING,
  project_id STRING NOT NULL,
  bid_id STRING,
  body STRING NOT NULL,
  kind STRING NOT NULL,
  source STRING NOT NULL,
  author STRING,
  created_at STRING NOT NULL,
  updated_at STRING NOT NULL
) USING DELTA;

-- Durable kb_build run record. `heartbeat_at` is what makes a dead build
-- distinguishable from a slow one (an app restart leaves no other trace).
CREATE TABLE IF NOT EXISTS {catalog}.bronze.mate_kb_build_job (
  id STRING,
  project_id STRING NOT NULL,
  status STRING NOT NULL,
  mode STRING NOT NULL,
  run_id STRING,
  message STRING,
  error STRING,
  attempt INT NOT NULL,
  heartbeat_at STRING,
  started_at STRING,
  finished_at STRING,
  created_at STRING NOT NULL,
  updated_at STRING NOT NULL
) USING DELTA;
