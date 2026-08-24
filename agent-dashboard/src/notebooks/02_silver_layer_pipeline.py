# Databricks notebook source
# MAGIC %run ./config_file

# COMMAND ----------

# MAGIC %python
# MAGIC spark.sql(f"USE CATALOG {UNITY_CATALOG}")
# MAGIC print(f"Active catalog: {UNITY_CATALOG}")

# COMMAND ----------
# DBTITLE 1,Install dependencies
# MAGIC %pip install openpyxl

# COMMAND ----------

# DBTITLE 1,Config + List Volume Files
# =============================================================================
# CONFIG
# =============================================================================
TARGET = SILVER
VOLUME = BRONZE_VOLUME.rstrip('/')

# List files in volume so we can identify exact filenames
print("Files in volume:")
files = dbutils.fs.ls(VOLUME)
for f in files:
    print(f"  {f.name}  ({f.size:,} bytes)")

# COMMAND ----------

# DBTITLE 1,Silver | silver_dim_environment
# MAGIC %sql
# MAGIC -- =============================================================================
# MAGIC -- SILVER : silver_dim_environment
# MAGIC -- SOURCE : silver.environment_level_credit_consumption (bronze)
# MAGIC -- GRAIN  : one row per distinct Power Platform environment
# MAGIC -- ROWS   : 5 (expected)
# MAGIC -- =============================================================================
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.silver_dim_environment AS
# MAGIC SELECT DISTINCT
# MAGIC     environment_id,
# MAGIC     environment_name,
# MAGIC     capacity_type
# MAGIC FROM silver.environment_level_credit_consumption
# MAGIC WHERE environment_id IS NOT NULL
# MAGIC   AND environment_id != '';
# MAGIC
# MAGIC SELECT * FROM silver.silver_dim_environment ORDER BY environment_name;

# COMMAND ----------

# DBTITLE 1,Silver normalize | sl_purview_log
# MAGIC %sql
# MAGIC -- =============================================================================
# MAGIC -- SILVER NORMALIZE : sl_purview_log
# MAGIC -- SOURCE : silver.microsoft_purview_audit_log  (bronze)
# MAGIC -- Maps PascalCase Purview export columns to snake_case for downstream SQL.
# MAGIC -- =============================================================================
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.sl_purview_log AS
# MAGIC SELECT
# MAGIC     RecordId                          AS record_id,
# MAGIC     CreationDate                      AS creation_date,
# MAGIC     CAST(RecordType AS BIGINT)        AS record_type,
# MAGIC     Operation                         AS operation,
# MAGIC     UserId                            AS user_id,
# MAGIC     AuditData                         AS audit_data,
# MAGIC     AssociatedAdminUnits              AS associated_admin_units,
# MAGIC     AssociatedAdminUnitsNames         AS associated_admin_units_names
# MAGIC FROM silver.microsoft_purview_audit_log
# MAGIC WHERE LENGTH(AuditData) > 200;

# COMMAND ----------

# DBTITLE 1,Silver | silver_fact_interactions
# MAGIC %sql
# MAGIC -- =============================================================================
# MAGIC -- SILVER : silver_fact_interactions
# MAGIC -- SOURCE : silver.sl_purview_log  (normalized Purview bronze)
# MAGIC -- GRAIN  : one row per M365 Copilot interaction event
# MAGIC -- KEY TRANSFORMS:
# MAGIC --   Most Copilot fields live under $.CopilotEventData.* (not JSON root).
# MAGIC --   interaction_type   : CASE on root AppIdentity pattern
# MAGIC --   uses_bing_search   : AISystemPlugin contains BingWebSearch
# MAGIC --   model_provider     : ModelTransparencyDetails[0].ModelProviderName
# MAGIC --   env_id             : REGEXP_EXTRACT Copilot.Studio.{guid} from AppIdentity
# MAGIC --   admin_unit_id/name : JSON array $[0] with fallback to raw string
# MAGIC -- =============================================================================
# MAGIC
# MAGIC CREATE OR REPLACE TABLE silver.silver_fact_interactions AS
# MAGIC SELECT
# MAGIC     -- Primary key & time
# MAGIC     b.record_id                                                                       AS record_id,
# MAGIC     TRY_TO_TIMESTAMP(b.creation_date)                                                 AS creation_ts,
# MAGIC     CAST(TRY_TO_TIMESTAMP(b.creation_date) AS DATE)                                   AS creation_date,
# MAGIC
# MAGIC     -- User
# MAGIC     b.user_id                                                                         AS user_email,
# MAGIC
# MAGIC     -- App identity & workload (root of audit_data JSON)
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.AppIdentity')                                    AS app_identity,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.Workload')                                       AS workload,
# MAGIC
# MAGIC     -- Network
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.ClientIP')                                       AS client_ip,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.ClientRegion')                                   AS client_region,
# MAGIC
# MAGIC     -- Agent (root AgentId; name prefers CopilotEventData.TargetAgentName)
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.AgentId')                                        AS agent_id,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.TargetAgentName'),
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.AgentName')
# MAGIC     )                                                                                 AS agent_name,
# MAGIC
# MAGIC     -- Surface / license / thread (nested under CopilotEventData)
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.AppHost')                       AS app_host,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.LicenseType')                   AS license_type,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.ThreadId')                      AS thread_id,
# MAGIC     GET_JSON_OBJECT(
# MAGIC         b.audit_data,
# MAGIC         '$.CopilotEventData.ModelTransparencyDetails[0].ModelProviderName'
# MAGIC     )                                                                                 AS model_provider,
# MAGIC
# MAGIC     -- Target (Declarative) agent
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.TargetAgentName'),
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.AgentName')
# MAGIC     )                                                                                 AS target_agent_name,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.TargetPlatformAgentId'),
# MAGIC         REGEXP_EXTRACT(
# MAGIC             GET_JSON_OBJECT(b.audit_data, '$.AppIdentity'),
# MAGIC             'Declarative\\.(T_[0-9a-fA-F-]+)',
# MAGIC             1
# MAGIC         )
# MAGIC     )                                                                                 AS target_agent_id,
# MAGIC
# MAGIC     -- Interaction type: derived from AppIdentity pattern (Declarative before Studio)
# MAGIC     CASE
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE '%Declarative%'
# MAGIC              THEN 'Declarative'
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'Copilot.Studio.%'
# MAGIC              THEN 'CustomEngine'
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'Copilot.M365Copilot.%'
# MAGIC           OR GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'Copilot.Fabric.%'
# MAGIC              THEN 'BizChat_M365'
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'MicrosoftAgent.%'
# MAGIC              THEN 'MicrosoftAgent'
# MAGIC         ELSE 'Other'
# MAGIC     END                                                                               AS interaction_type,
# MAGIC
# MAGIC     -- Bing: AISystemPlugin Id = BingWebSearch (nested under CopilotEventData)
# MAGIC     CASE
# MAGIC         WHEN COALESCE(
# MAGIC                 GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.AISystemPlugin'),
# MAGIC                 ''
# MAGIC              ) LIKE '%BingWebSearch%'
# MAGIC           OR LOWER(GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.HasBingWebSearch')) = 'true'
# MAGIC           OR LOWER(GET_JSON_OBJECT(b.audit_data, '$.HasBingWebSearch')) = 'true'
# MAGIC         THEN TRUE ELSE FALSE
# MAGIC     END                                                                               AS uses_bing_search,
# MAGIC
# MAGIC     CASE
# MAGIC         WHEN LOWER(COALESCE(
# MAGIC                 GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.JailbreakDetected'),
# MAGIC                 GET_JSON_OBJECT(b.audit_data, '$.JailbreakDetected')
# MAGIC              )) = 'true'
# MAGIC         THEN TRUE ELSE FALSE
# MAGIC     END                                                                               AS jailbreak_detected,
# MAGIC
# MAGIC     -- Environment: UUID after Copilot.Studio. (CustomEngine only; '' otherwise)
# MAGIC     COALESCE(
# MAGIC         REGEXP_EXTRACT(
# MAGIC             GET_JSON_OBJECT(b.audit_data, '$.AppIdentity'),
# MAGIC             'Copilot\\.Studio\\.([0-9a-fA-F-]{36})',
# MAGIC             1
# MAGIC         ),
# MAGIC         ''
# MAGIC     )                                                                                 AS env_id,
# MAGIC
# MAGIC     -- Admin unit: associated_admin_units stored as JSON array ["guid"] or plain string
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.associated_admin_units,     '$[0]'),
# MAGIC         b.associated_admin_units
# MAGIC     )                                                                                 AS admin_unit_id,
# MAGIC
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.associated_admin_units_names, '$[0]'),
# MAGIC         b.associated_admin_units_names
# MAGIC     )                                                                                 AS admin_unit_name
# MAGIC
# MAGIC FROM silver.sl_purview_log b;
# MAGIC
# MAGIC -- Verify row count and sample
# MAGIC SELECT COUNT(*) AS total_rows FROM silver.silver_fact_interactions;