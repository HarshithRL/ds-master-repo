# Mate Unity Catalog (bronze) backend

Optional persistence for Mate app data in Unity Catalog Delta tables + a UC volume for files.
Lakebase schema mate_agent stays for LangGraph checkpoints only. Comparison Deep Agent / emit / ComparisonMatrix and Excel persist are unchanged.

## Catalogs

| Target | Catalog (MATE_UC_CATALOG / ar.catalog) |
|--------|--------------------------------------------|
| D / T  | utomation_d |
| A      | utomation_a |
| P      | utomation_p |

Never hardcode utomation_d in Python — always read MATE_UC_CATALOG.

## Layout

- Schema: ronze
- Tables: {catalog}.bronze.mate_* (see ddl_mate_bronze.sql)
- Files: /Volumes/{catalog}/bronze/bronze_volume/mate/{project_id}/...
  Env: MATE_UC_SCHEMA=bronze, MATE_UC_VOLUME=bronze_volume

## Run DDL

1. Pick the catalog for the workspace (utomation_d / _a / _p).
2. In a SQL warehouse notebook or DBSQL editor, substitute {catalog} in ddl_mate_bronze.sql (or USE CATALOG / USE SCHEMA bronze and strip the catalog prefix).
3. Execute the script (idempotent CREATE TABLE IF NOT EXISTS).
4. Confirm the volume {catalog}.bronze.bronze_volume exists and the app SP has WRITE VOLUME.

## Flip the flag

Local / tests (default — no behavior change):

`	ext
MATE_DB_BACKEND=sqlite   # or unset
`

Deployed UC cutover (after DDL + warehouse/volume attachments):

`	ext
MATE_DB_BACKEND=uc
MATE_UC_CATALOG=<var.catalog>
MATE_UC_SCHEMA=bronze
MATE_UC_VOLUME=bronze_volume
DATABRICKS_WAREHOUSE_ID=<sql warehouse id>   # from app resource valueFrom
`

Bundle defaults keep MATE_DB_BACKEND=sqlite until cutover. Set MATE_DB_BACKEND=uc in pp.yaml / app config when ready.

## Packages

UC SQLAlchemy access uses databricks-sql-connector (host/http_path/token from Apps env + DATABRICKS_WAREHOUSE_ID). databricks-sdk remains for workspace auth defaults.
