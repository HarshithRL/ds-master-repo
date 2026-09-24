# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,02 - Silver & Dimensional Layer
# MAGIC %md
# MAGIC # 02 - Silver & Dimensional Layer
# MAGIC
# MAGIC **Purpose:** Transforms bronze tables into silver normalize tables, then builds the full dimensional model (dims, facts, views) in `${pipeline_schema}`.
# MAGIC
# MAGIC **Run after:** `01_bronze_ingestion`
# MAGIC **Run before:** `03_metrics_validate_publish`

# COMMAND ----------

# DBTITLE 1,Config
dbutils.widgets.text("catalog", "automation_d", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
S = f"{CATALOG}.silver"  # shorthand for all SQL
dbutils.widgets.text("pipeline_schema", S, "Pipeline Schema")
print(f"Target schema: {S}")

# COMMAND ----------

# DBTITLE 1,Silver | sl_purview_log
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.sl_purview_log AS
# MAGIC SELECT
# MAGIC     RecordId                          AS record_id,
# MAGIC     CreationDate                      AS creation_date,
# MAGIC     CAST(RecordType AS BIGINT)        AS record_type,
# MAGIC     Operation                         AS operation,
# MAGIC     UserId                            AS user_id,
# MAGIC     AuditData                         AS audit_data,
# MAGIC     AssociatedAdminUnits              AS associated_admin_units,
# MAGIC     AssociatedAdminUnitsNames         AS associated_admin_units_names
# MAGIC FROM ${pipeline_schema}.microsoft_purview_audit_log
# MAGIC WHERE LENGTH(AuditData) > 200;

# COMMAND ----------

# DBTITLE 1,Silver | silver_dim_environment
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.silver_dim_environment AS
# MAGIC SELECT DISTINCT
# MAGIC     environment_id,
# MAGIC     environment_name,
# MAGIC     capacity_type
# MAGIC FROM ${pipeline_schema}.environment_level_credit_consumption
# MAGIC WHERE environment_id IS NOT NULL AND environment_id != '';

# COMMAND ----------

# DBTITLE 1,Silver | silver_fact_interactions
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.silver_fact_interactions AS
# MAGIC SELECT
# MAGIC     b.record_id,
# MAGIC     TRY_TO_TIMESTAMP(b.creation_date)                                                 AS creation_ts,
# MAGIC     CAST(TRY_TO_TIMESTAMP(b.creation_date) AS DATE)                                   AS creation_date,
# MAGIC     b.user_id                                                                         AS user_email,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.AppIdentity')                                    AS app_identity,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.Workload')                                       AS workload,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.ClientIP')                                       AS client_ip,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.ClientRegion')                                   AS client_region,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.AgentId')                                        AS agent_id,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.TargetAgentName'),
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.AgentName')
# MAGIC     )                                                                                 AS agent_name,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.AppHost')                       AS app_host,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.LicenseType')                   AS license_type,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.ThreadId')                      AS thread_id,
# MAGIC     GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.ModelTransparencyDetails[0].ModelProviderName') AS model_provider,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.TargetAgentName'),
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.AgentName')
# MAGIC     )                                                                                 AS target_agent_name,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.TargetPlatformAgentId'),
# MAGIC         REGEXP_EXTRACT(GET_JSON_OBJECT(b.audit_data, '$.AppIdentity'), 'Declarative\\.(T_[0-9a-fA-F-]+)', 1)
# MAGIC     )                                                                                 AS target_agent_id,
# MAGIC     CASE
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE '%Declarative%' THEN 'Declarative'
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'Copilot.Studio.%' THEN 'CustomEngine'
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'Copilot.M365Copilot.%'
# MAGIC           OR GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'Copilot.Fabric.%' THEN 'BizChat_M365'
# MAGIC         WHEN GET_JSON_OBJECT(b.audit_data, '$.AppIdentity') LIKE 'MicrosoftAgent.%' THEN 'MicrosoftAgent'
# MAGIC         ELSE 'Other'
# MAGIC     END                                                                               AS interaction_type,
# MAGIC     CASE
# MAGIC         WHEN COALESCE(GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.AISystemPlugin'), '') LIKE '%BingWebSearch%'
# MAGIC           OR LOWER(GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.HasBingWebSearch')) = 'true'
# MAGIC           OR LOWER(GET_JSON_OBJECT(b.audit_data, '$.HasBingWebSearch')) = 'true'
# MAGIC         THEN TRUE ELSE FALSE
# MAGIC     END                                                                               AS uses_bing_search,
# MAGIC     CASE
# MAGIC         WHEN LOWER(COALESCE(
# MAGIC                 GET_JSON_OBJECT(b.audit_data, '$.CopilotEventData.JailbreakDetected'),
# MAGIC                 GET_JSON_OBJECT(b.audit_data, '$.JailbreakDetected')
# MAGIC              )) = 'true'
# MAGIC         THEN TRUE ELSE FALSE
# MAGIC     END                                                                               AS jailbreak_detected,
# MAGIC     COALESCE(
# MAGIC         REGEXP_EXTRACT(GET_JSON_OBJECT(b.audit_data, '$.AppIdentity'), 'Copilot\\.Studio\\.([0-9a-fA-F-]{36})', 1),
# MAGIC         ''
# MAGIC     )                                                                                 AS env_id,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.associated_admin_units, '$[0]'),
# MAGIC         b.associated_admin_units
# MAGIC     )                                                                                 AS admin_unit_id,
# MAGIC     COALESCE(
# MAGIC         GET_JSON_OBJECT(b.associated_admin_units_names, '$[0]'),
# MAGIC         b.associated_admin_units_names
# MAGIC     )                                                                                 AS admin_unit_name
# MAGIC FROM ${pipeline_schema}.sl_purview_log b;

# COMMAND ----------

# DBTITLE 1,Silver | sl_agent_inventory
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.sl_agent_inventory AS
# MAGIC SELECT
# MAGIC   Item_name AS item_name, Created_in AS created_in, Item_ID AS item_id,
# MAGIC   Owner AS owner, Model AS model,
# MAGIC   Authentication AS authentication, Orchestration AS orchestration,
# MAGIC   Microsoft_Entra_Agent_ID AS microsoft_entra_agent_id,
# MAGIC   Blueprint_ID AS blueprint_id,
# MAGIC   Created_On AS created_on, Published_On AS published_on,
# MAGIC   Created_By AS created_by
# MAGIC FROM ${pipeline_schema}.agents_inventory;

# COMMAND ----------

# DBTITLE 1,Silver | sl_agent_credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.sl_agent_credit AS
# MAGIC SELECT
# MAGIC   Agent_Name AS agent_name, Agent_Id AS agent_id, Product AS product,
# MAGIC   AI_Feature_Billable_Feature AS ai_feature_billable_feature,
# MAGIC   CAST(ROUND(TRY_CAST(Billed_credit AS DOUBLE), 0) AS BIGINT) AS billed_credit,
# MAGIC   CAST(Non_billed_credit AS DECIMAL(21,1)) AS non_billed_credit,
# MAGIC   Channel AS channel, Knowledge_Sources AS knowledge_sources,
# MAGIC   Tool_Used AS tool_used, LLM_Model AS llm_model,
# MAGIC   Environment_Name AS environment_name
# MAGIC FROM ${pipeline_schema}.agent_level_credit_consumption;

# COMMAND ----------

# DBTITLE 1,Silver | sl_environment_credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.sl_environment_credit AS
# MAGIC SELECT
# MAGIC   BillingPlan_Id AS billing_plan_id, BillingPlan_Name AS billing_plan_name,
# MAGIC   Environment_Id AS environment_id, Environment_Name AS environment_name,
# MAGIC   Capacity_Type AS capacity_type,
# MAGIC   CAST(ROUND(TRY_CAST(Entitled_Quantity AS DOUBLE), 0) AS BIGINT) AS entitled_quantity,
# MAGIC   CAST(ROUND(TRY_CAST(Prepaid_Consumed_Quantity AS DOUBLE), 0) AS BIGINT) AS prepaid_consumed_quantity,
# MAGIC   CAST(ROUND(TRY_CAST(Pay_As_You_Go_Consumed_Quantity AS DOUBLE), 0) AS BIGINT) AS pay_as_you_go_consumed_quantity,
# MAGIC   COALESCE(to_date(Usage_Date, 'M/d/yyyy h:mm:ss a'), to_date(Usage_Date, 'M/d/yyyy'), to_date(SPLIT(Usage_Date, ' ')[0], 'M/d/yyyy'), to_date(Usage_Date)) AS usage_date,
# MAGIC   DATE_FORMAT(COALESCE(to_date(Usage_Date, 'M/d/yyyy h:mm:ss a'), to_date(Usage_Date, 'M/d/yyyy'), to_date(SPLIT(Usage_Date, ' ')[0], 'M/d/yyyy'), to_date(Usage_Date)), 'dd/MM/yyyy') AS usage_date_eu
# MAGIC FROM ${pipeline_schema}.environment_level_credit_consumption;

# COMMAND ----------

# DBTITLE 1,Silver | sl_user_credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.sl_user_credit AS
# MAGIC SELECT
# MAGIC   User_Id AS user_id, User_Email AS user_email,
# MAGIC   Agent_Id AS agent_id, Agent_Name AS agent_name,
# MAGIC   CAST(ROUND(TRY_CAST(Billable_credit_used AS DOUBLE), 0) AS BIGINT) AS billable_credit_used,
# MAGIC   CAST(Credits_used AS DECIMAL(21,1)) AS credits_used,
# MAGIC   M365_Copilot_Licensed AS m365_copilot_licensed
# MAGIC FROM ${pipeline_schema}.user_level_credit_consumption;

# COMMAND ----------

# DBTITLE 1,Reference | ref_credit_rate
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.ref_credit_rate AS
# MAGIC SELECT
# MAGIC   CAST(0.006932 AS DOUBLE)  AS credit_to_eur,
# MAGIC   'EUR'                     AS currency,
# MAGIC   DATE'2026-06-29'          AS effective_date,
# MAGIC   'Microsoft Copilot Studio prepaid pack: EUR 173.30 / 25,000 credits (ex-VAT).' AS notes;

# COMMAND ----------

# DBTITLE 1,Dimension | dim_date
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.dim_date AS
# MAGIC SELECT
# MAGIC   CAST(DATE_FORMAT(d, 'yyyyMMdd') AS INT) AS date_key,
# MAGIC   d AS date,
# MAGIC   DATE_FORMAT(d, 'dd/MM/yyyy') AS date_eu,
# MAGIC   YEAR(d) AS year, MONTH(d) AS month, DAY(d) AS day,
# MAGIC   DATE_FORMAT(d, 'MMMM') AS month_name,
# MAGIC   QUARTER(d) AS quarter,
# MAGIC   WEEKOFYEAR(d) AS week_of_year,
# MAGIC   DATE_FORMAT(d, 'EEEE') AS day_name
# MAGIC FROM (SELECT EXPLODE(SEQUENCE(DATE'2020-01-01', DATE'2030-12-31', INTERVAL 1 DAY)) AS d);

# COMMAND ----------

# DBTITLE 1,Dimension | dim_user
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.dim_user AS
# MAGIC SELECT
# MAGIC   XXHASH64(user_id) AS user_key,
# MAGIC   user_id, user_email, m365_copilot_licensed
# MAGIC FROM (
# MAGIC   SELECT DISTINCT user_id, LOWER(user_email) AS user_email, m365_copilot_licensed
# MAGIC   FROM ${pipeline_schema}.sl_user_credit
# MAGIC );

# COMMAND ----------

# DBTITLE 1,Dimension | dim_environment
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.dim_environment AS
# MAGIC WITH inv AS (
# MAGIC   SELECT LOWER(Environment_Name) AS environment_name_norm, Environment_Name AS environment_name,
# MAGIC          NULLIF(NULLIF(Environment_ID, ''), '-') AS environment_id,
# MAGIC          NULLIF(NULLIF(Environment_Type, ''), '-') AS environment_type,
# MAGIC          NULLIF(NULLIF(Location, ''), '-') AS environment_region,
# MAGIC          CASE WHEN LOWER(COALESCE(Managed_State, '')) IN ('true','yes','1','managed') THEN TRUE ELSE FALSE END AS is_managed
# MAGIC   FROM ${pipeline_schema}.copilot_studio_kit_all_records
# MAGIC   WHERE Environment_Name IS NOT NULL AND Environment_Name != ''
# MAGIC ),
# MAGIC ranked AS (
# MAGIC   SELECT *, ROW_NUMBER() OVER (PARTITION BY environment_name_norm ORDER BY environment_id DESC NULLS LAST) AS rn
# MAGIC   FROM inv
# MAGIC )
# MAGIC SELECT
# MAGIC   XXHASH64(environment_name_norm) AS environment_key,
# MAGIC   environment_id, environment_name, environment_type, environment_region, is_managed
# MAGIC FROM ranked WHERE rn = 1;

# COMMAND ----------

# DBTITLE 1,Dimension | dim_agent
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.dim_agent AS
# MAGIC WITH dedup AS (SELECT * FROM ${pipeline_schema}.sl_agent_inventory),
# MAGIC parsed_all AS (
# MAGIC   SELECT
# MAGIC     item_id, item_name, created_in,
# MAGIC     NULLIF(owner, '-') AS owner,
# MAGIC     NULLIF(model, '-') AS model, NULLIF(authentication, '-') AS authentication,
# MAGIC     NULLIF(orchestration, '-') AS orchestration,
# MAGIC     microsoft_entra_agent_id, blueprint_id,
# MAGIC     to_date(created_on, 'M/d/yyyy h:mm:ss a') AS created_on_date,
# MAGIC     to_date(published_on, 'M/d/yyyy h:mm:ss a') AS published_on_date,
# MAGIC     created_by
# MAGIC   FROM dedup
# MAGIC ),
# MAGIC kit AS (
# MAGIC   SELECT Agent_ID AS agent_id, Name AS agent_name, Agent_Owner AS agent_owner,
# MAGIC          Environment_Name AS environment, Environment_Type AS environment_type,
# MAGIC          Location AS environment_region,
# MAGIC          CASE WHEN LOWER(COALESCE(Managed_State, '')) IN ('true','yes','1','managed') THEN TRUE ELSE FALSE END AS is_managed
# MAGIC   FROM ${pipeline_schema}.copilot_studio_kit_all_records
# MAGIC ),
# MAGIC credit_agents AS (
# MAGIC   SELECT LOWER(agent_name) AS agent_name_norm, agent_name,
# MAGIC          MAX(CASE WHEN product = 'Dataverse' THEN 'Platform Tool' ELSE 'Copilot Studio' END) AS agent_category
# MAGIC   FROM ${pipeline_schema}.sl_agent_credit GROUP BY LOWER(agent_name), agent_name
# MAGIC ),
# MAGIC used_agents AS (
# MAGIC   SELECT LOWER(agent_name) AS agent_name_norm FROM ${pipeline_schema}.sl_user_credit GROUP BY LOWER(agent_name)
# MAGIC ),
# MAGIC enriched AS (
# MAGIC   SELECT p.*,
# MAGIC     DATE_FORMAT(p.created_on_date, 'dd/MM/yyyy') AS created_on_eu,
# MAGIC     YEAR(p.created_on_date) AS created_year, MONTH(p.created_on_date) AS created_month,
# MAGIC     DATE_FORMAT(p.published_on_date, 'dd/MM/yyyy') AS published_on_eu,
# MAGIC     XXHASH64(p.item_id) AS agent_key, p.item_id AS agent_id,
# MAGIC     p.item_name AS agent_name,
# MAGIC     COALESCE(ca.agent_category, 'Copilot Studio') AS agent_category,
# MAGIC     ca.agent_name AS credit_agent_name,
# MAGIC     COALESCE(k.environment, p.created_in) AS environment_name,
# MAGIC     k.environment_type, k.environment_region, COALESCE(k.is_managed, FALSE) AS is_managed,
# MAGIC     XXHASH64(LOWER(COALESCE(k.environment, p.created_in))) AS environment_key,
# MAGIC     CASE WHEN LOWER(COALESCE(p.created_in, '')) LIKE '%agent builder%' THEN 'Agent Builder' ELSE 'Copilot Studio' END AS platform,
# MAGIC     CASE WHEN NULLIF(p.created_by, '-') IS NOT NULL THEN TRUE ELSE FALSE END AS is_valid_agent,
# MAGIC     CASE WHEN LOWER(COALESCE(p.authentication, '-')) IN ('-', 'none', 'no authentication') THEN TRUE ELSE FALSE END AS is_no_auth,
# MAGIC     (ua.agent_name_norm IS NOT NULL) AS is_used
# MAGIC   FROM parsed_all p
# MAGIC   LEFT JOIN kit k ON k.agent_id = p.item_id
# MAGIC   LEFT JOIN credit_agents ca ON ca.agent_name_norm = LOWER(p.item_name)
# MAGIC   LEFT JOIN used_agents ua ON ua.agent_name_norm = LOWER(p.item_name)
# MAGIC )
# MAGIC SELECT * FROM enriched;

# COMMAND ----------

# DBTITLE 1,Bridge | _agent_name_bridge
# MAGIC %sql
# MAGIC -- Agent name bridge for fuzzy join between credit tables and inventory
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}._agent_name_bridge AS
# MAGIC SELECT
# MAGIC   LOWER(a.agent_name) AS agent_name_norm,
# MAGIC   a.agent_key,
# MAGIC   a.agent_name AS inventory_agent_name
# MAGIC FROM ${pipeline_schema}.dim_agent a
# MAGIC WHERE a.is_valid_agent;

# COMMAND ----------

# DBTITLE 1,Fact | fact_environment_credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.fact_environment_credit AS
# MAGIC WITH parsed AS (
# MAGIC   SELECT environment_id, environment_name, capacity_type,
# MAGIC          prepaid_consumed_quantity, entitled_quantity, pay_as_you_go_consumed_quantity,
# MAGIC          usage_date, usage_date_eu
# MAGIC   FROM ${pipeline_schema}.sl_environment_credit
# MAGIC   WHERE usage_date IS NOT NULL
# MAGIC )
# MAGIC SELECT
# MAGIC   XXHASH64(LOWER(p.environment_name)) AS environment_key,
# MAGIC   CAST(DATE_FORMAT(p.usage_date, 'yyyyMMdd') AS INT) AS date_key,
# MAGIC   p.environment_name, p.capacity_type,
# MAGIC   p.prepaid_consumed_quantity, p.entitled_quantity, p.pay_as_you_go_consumed_quantity,
# MAGIC   p.usage_date, p.usage_date_eu
# MAGIC FROM parsed p;

# COMMAND ----------

# DBTITLE 1,Fact | fact_agent_credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.fact_agent_credit AS
# MAGIC SELECT
# MAGIC   XXHASH64(LOWER(c.environment_name)) AS environment_key,
# MAGIC   CASE WHEN c.product = 'Copilot Studio' THEN b.agent_key END AS inventory_agent_key,
# MAGIC   c.agent_id AS credit_agent_id,
# MAGIC   c.agent_name,
# MAGIC   COALESCE(
# MAGIC     CASE WHEN c.product = 'Dataverse' THEN 'Platform Tool' ELSE 'Copilot Studio' END,
# MAGIC     'Copilot Studio'
# MAGIC   ) AS agent_category,
# MAGIC   c.product,
# MAGIC   c.ai_feature_billable_feature AS ai_feature,
# MAGIC   c.channel,
# MAGIC   c.knowledge_sources,
# MAGIC   c.tool_used,
# MAGIC   c.llm_model,
# MAGIC   c.environment_name,
# MAGIC   c.billed_credit,
# MAGIC   c.non_billed_credit
# MAGIC FROM ${pipeline_schema}.sl_agent_credit c
# MAGIC LEFT JOIN ${pipeline_schema}._agent_name_bridge b ON b.agent_name_norm = LOWER(c.agent_name);

# COMMAND ----------

# DBTITLE 1,Fact | fact_user_agent_credit
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.fact_user_agent_credit AS
# MAGIC WITH bridge AS (
# MAGIC   SELECT agent_name_norm, agent_key FROM ${pipeline_schema}._agent_name_bridge
# MAGIC )
# MAGIC SELECT
# MAGIC   u.user_key,
# MAGIC   b.agent_key AS inventory_agent_key,
# MAGIC   c.agent_id AS credit_agent_id,
# MAGIC   c.agent_name,
# MAGIC   COALESCE(ac.agent_category, 'Copilot Studio') AS agent_category,
# MAGIC   c.billable_credit_used,
# MAGIC   c.credits_used
# MAGIC FROM ${pipeline_schema}.sl_user_credit c
# MAGIC INNER JOIN ${pipeline_schema}.dim_user u ON u.user_id = c.user_id
# MAGIC LEFT JOIN bridge b ON b.agent_name_norm = LOWER(c.agent_name)
# MAGIC LEFT JOIN (
# MAGIC   SELECT LOWER(agent_name) AS agent_name_norm,
# MAGIC          MAX(CASE WHEN product = 'Dataverse' THEN 'Platform Tool' ELSE 'Copilot Studio' END) AS agent_category
# MAGIC   FROM ${pipeline_schema}.sl_agent_credit GROUP BY LOWER(agent_name)
# MAGIC ) ac ON ac.agent_name_norm = LOWER(c.agent_name);

# COMMAND ----------

# DBTITLE 1,Fact | fact_agent_knowledge_source
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.fact_agent_knowledge_source AS
# MAGIC WITH inv AS (SELECT DISTINCT item_id FROM ${pipeline_schema}.sl_agent_inventory),
# MAGIC kit AS (
# MAGIC   SELECT Agent_ID AS agent_id, Name AS agent_name, Agent_Owner AS agent_owner,
# MAGIC          Agent_Owner_Email AS agent_owner_email, Environment_Name AS environment_name,
# MAGIC          Environment_Type AS environment_type, Published AS published,
# MAGIC          Agent_Created_By AS created_by, Model AS model, Knowledge_Sources AS knowledge_sources_raw
# MAGIC   FROM ${pipeline_schema}.copilot_studio_kit_all_records
# MAGIC ),
# MAGIC exploded AS (
# MAGIC   SELECT k.*, kb.DisplayName AS kb_display_name, kb.KnowledgeType AS kb_type, kb.Value AS kb_value
# MAGIC   FROM kit k
# MAGIC   LATERAL VIEW EXPLODE(
# MAGIC     FROM_JSON(
# MAGIC       CASE WHEN k.knowledge_sources_raw IS NULL OR k.knowledge_sources_raw IN ('', '-', '[]') THEN '[]' ELSE k.knowledge_sources_raw END,
# MAGIC       'ARRAY<STRUCT<DisplayName:STRING,KnowledgeType:STRING,Value:STRING>>'
# MAGIC     )
# MAGIC   ) t AS kb
# MAGIC   WHERE kb.Value IS NOT NULL
# MAGIC ),
# MAGIC kb_counts AS (SELECT kb_value, COUNT(DISTINCT agent_id) AS kb_agent_count FROM exploded GROUP BY kb_value)
# MAGIC SELECT e.agent_id, e.agent_name, e.agent_owner, e.agent_owner_email,
# MAGIC        e.environment_name, e.environment_type, e.published, e.created_by, e.model,
# MAGIC        MD5(e.kb_value) AS kb_key, e.kb_display_name, e.kb_type, e.kb_value,
# MAGIC        c.kb_agent_count, (c.kb_agent_count > 1) AS is_shared,
# MAGIC        (i.item_id IS NOT NULL) AS in_inventory,
# MAGIC        (da.is_valid_agent AND da.platform = 'Copilot Studio') AS is_valid_studio
# MAGIC FROM exploded e
# MAGIC INNER JOIN kb_counts c ON c.kb_value = e.kb_value
# MAGIC LEFT JOIN inv i ON i.item_id = e.agent_id
# MAGIC LEFT JOIN ${pipeline_schema}.dim_agent da ON da.agent_id = e.agent_id;

# COMMAND ----------

# DBTITLE 1,View | vw_agent_governance
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.vw_agent_governance AS
# MAGIC WITH env_credit AS (
# MAGIC   SELECT DISTINCT LOWER(environment_name) AS environment_name_norm
# MAGIC   FROM ${pipeline_schema}.sl_environment_credit
# MAGIC )
# MAGIC SELECT
# MAGIC   d.agent_key, d.agent_id, d.agent_name, d.platform, d.agent_category,
# MAGIC   d.status, d.owner, d.created_by, d.model, d.authentication, d.orchestration,
# MAGIC   d.created_on_date, d.created_on_eu, d.created_year, d.created_month,
# MAGIC   d.published_on_date, d.published_on_eu,
# MAGIC   DATEDIFF(CURRENT_DATE(), d.created_on_date) AS agent_age_in_days,
# MAGIC   d.is_valid_agent, d.is_no_auth, d.is_used,
# MAGIC   CASE WHEN d.is_used THEN 'Used' ELSE 'Dormant' END AS usage_status,
# MAGIC   d.credit_agent_name, d.environment_name, d.environment_type, d.environment_region,
# MAGIC   e.environment_id, d.is_managed,
# MAGIC   (ec.environment_name_norm IS NOT NULL) AS environment_has_credit
# MAGIC FROM ${pipeline_schema}.dim_agent d
# MAGIC LEFT JOIN ${pipeline_schema}.dim_environment e ON e.environment_key = d.environment_key
# MAGIC LEFT JOIN env_credit ec ON ec.environment_name_norm = LOWER(d.environment_name);

# COMMAND ----------

# DBTITLE 1,View | vw_agent_knowledge
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.vw_agent_knowledge AS
# MAGIC WITH inv AS (SELECT DISTINCT item_id FROM ${pipeline_schema}.sl_agent_inventory),
# MAGIC kit AS (
# MAGIC   SELECT Agent_ID AS agent_id, Name AS agent_name, Agent_Owner AS agent_owner,
# MAGIC          Agent_Owner_Email AS agent_owner_email, Environment_Name AS environment_name,
# MAGIC          Environment_Type AS environment_type, Published AS published,
# MAGIC          Agent_Created_By AS created_by, Model AS model,
# MAGIC          Knowledge_Sources AS knowledge_sources_raw,
# MAGIC          Uses_Knowledge_Sources AS uses_knowledge_flag,
# MAGIC          Web_Search_Enabled AS web_search_enabled
# MAGIC   FROM ${pipeline_schema}.copilot_studio_kit_all_records
# MAGIC ),
# MAGIC parsed AS (
# MAGIC   SELECT k.*,
# MAGIC     CASE WHEN k.knowledge_sources_raw IS NULL OR k.knowledge_sources_raw IN ('', '-', '[]') THEN 0
# MAGIC     ELSE SIZE(FROM_JSON(k.knowledge_sources_raw, 'ARRAY<STRUCT<DisplayName:STRING,KnowledgeType:STRING,Value:STRING>>'))
# MAGIC     END AS knowledge_source_count
# MAGIC   FROM kit k
# MAGIC ),
# MAGIC da AS (SELECT agent_id, is_valid_agent, platform FROM ${pipeline_schema}.dim_agent)
# MAGIC SELECT p.agent_id, p.agent_name, p.agent_owner, p.agent_owner_email,
# MAGIC        p.environment_name, p.environment_type, p.published, p.created_by, p.model,
# MAGIC        p.uses_knowledge_flag, p.web_search_enabled, p.knowledge_source_count,
# MAGIC        (p.knowledge_source_count > 0) AS has_knowledge_sources,
# MAGIC        (p.knowledge_sources_raw IS NULL OR p.knowledge_sources_raw IN ('', '-')) AS is_detail_unavailable,
# MAGIC        (i.item_id IS NOT NULL) AS in_inventory,
# MAGIC        (d.is_valid_agent AND d.platform = 'Copilot Studio') AS is_valid_studio
# MAGIC FROM parsed p
# MAGIC LEFT JOIN inv i ON i.item_id = p.agent_id
# MAGIC LEFT JOIN da d ON d.agent_id = p.agent_id;

# COMMAND ----------

# DBTITLE 1,View | vw_agent_credit_detail
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.vw_agent_credit_detail AS
# MAGIC WITH rate AS (SELECT MAX(credit_to_eur) AS credit_to_eur FROM ${pipeline_schema}.ref_credit_rate),
# MAGIC bridge AS (SELECT agent_name_norm, agent_key, inventory_agent_name FROM ${pipeline_schema}._agent_name_bridge)
# MAGIC SELECT
# MAGIC   f.credit_agent_id, f.agent_name, f.agent_category, f.product, f.ai_feature, f.channel,
# MAGIC   f.knowledge_sources, f.tool_used, f.llm_model, f.environment_name,
# MAGIC   e.environment_type, e.environment_region,
# MAGIC   COALESCE(b.inventory_agent_name, '') AS inventory_agent_name,
# MAGIC   COALESCE(d.platform, '') AS platform,
# MAGIC   f.billed_credit, f.non_billed_credit,
# MAGIC   CAST(f.billed_credit + f.non_billed_credit AS DECIMAL(22, 1)) AS total_credit,
# MAGIC   CAST((f.billed_credit + f.non_billed_credit) * r.credit_to_eur AS DOUBLE) AS total_credit_cost_eur
# MAGIC FROM ${pipeline_schema}.fact_agent_credit f
# MAGIC CROSS JOIN rate r
# MAGIC LEFT JOIN ${pipeline_schema}.dim_environment e ON e.environment_key = f.environment_key
# MAGIC LEFT JOIN bridge b ON b.agent_key = f.inventory_agent_key
# MAGIC LEFT JOIN ${pipeline_schema}.dim_agent d ON d.agent_key = f.inventory_agent_key;

# COMMAND ----------

# DBTITLE 1,View | vw_environment_daily
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.vw_environment_daily AS
# MAGIC WITH rate AS (SELECT MAX(credit_to_eur) AS credit_to_eur FROM ${pipeline_schema}.ref_credit_rate)
# MAGIC SELECT
# MAGIC   f.environment_name, e.environment_type, e.environment_region, e.is_managed,
# MAGIC   f.usage_date AS date, f.usage_date_eu AS date_eu,
# MAGIC   dd.year, dd.month, dd.month_name, dd.quarter, dd.week_of_year,
# MAGIC   f.capacity_type,
# MAGIC   f.prepaid_consumed_quantity, f.entitled_quantity, f.pay_as_you_go_consumed_quantity,
# MAGIC   CAST(f.prepaid_consumed_quantity * r.credit_to_eur AS DOUBLE) AS prepaid_cost_eur
# MAGIC FROM ${pipeline_schema}.fact_environment_credit f
# MAGIC CROSS JOIN rate r
# MAGIC LEFT JOIN ${pipeline_schema}.dim_environment e ON e.environment_key = f.environment_key
# MAGIC LEFT JOIN ${pipeline_schema}.dim_date dd ON dd.date_key = f.date_key;

# COMMAND ----------

# DBTITLE 1,View | vw_user_agent_usage
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.vw_user_agent_usage AS
# MAGIC WITH rate AS (SELECT MAX(credit_to_eur) AS credit_to_eur FROM ${pipeline_schema}.ref_credit_rate),
# MAGIC bridge AS (SELECT agent_name_norm, agent_key, inventory_agent_name FROM ${pipeline_schema}._agent_name_bridge)
# MAGIC SELECT
# MAGIC   f.user_key, u.user_email, u.m365_copilot_licensed,
# MAGIC   f.credit_agent_id, f.agent_name, f.agent_category,
# MAGIC   f.inventory_agent_key,
# MAGIC   b.inventory_agent_name,
# MAGIC   COALESCE(d.platform, '') AS platform,
# MAGIC   COALESCE(d.is_valid_agent, FALSE) AS is_valid_agent,
# MAGIC   f.billable_credit_used, f.credits_used,
# MAGIC   CAST(f.credits_used * r.credit_to_eur AS DOUBLE) AS consumption_cost_eur,
# MAGIC   CAST(f.billable_credit_used * r.credit_to_eur AS DOUBLE) AS spend_cost_eur
# MAGIC FROM ${pipeline_schema}.fact_user_agent_credit f
# MAGIC CROSS JOIN rate r
# MAGIC INNER JOIN ${pipeline_schema}.dim_user u ON u.user_key = f.user_key
# MAGIC LEFT JOIN bridge b ON b.agent_key = f.inventory_agent_key
# MAGIC LEFT JOIN ${pipeline_schema}.dim_agent d ON d.agent_key = f.inventory_agent_key;

# COMMAND ----------

# DBTITLE 1,Bot usage | bot_usage
# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE ${pipeline_schema}.bot_usage AS
# MAGIC SELECT
# MAGIC   k.Do_Not_Modify_PVA_Bot_Usage AS pva_bot_usage_id,
# MAGIC   k.Do_Not_Modify_Row_Checksum AS row_checksum,
# MAGIC   TRY_TO_TIMESTAMP(k.Do_Not_Modify_Modified_On) AS system_modified_on,
# MAGIC   k.Bot_Environment_Display_Name_PVA_Bot_PVA_Bot AS environment,
# MAGIC   k.PVA_Bot AS bot_name,
# MAGIC   COALESCE(
# MAGIC     to_date(k.Date, 'yyyy-MM-dd HH:mm:ss'),
# MAGIC     to_date(k.Date, 'M/d/yyyy'),
# MAGIC     to_date(k.Date, 'M/d/yy')
# MAGIC   ) AS usage_date,
# MAGIC   CAST(ROUND(TRY_CAST(k.Conversations AS DOUBLE), 0) AS BIGINT) AS conversations,
# MAGIC   TRY_TO_TIMESTAMP(k.Created_On) AS created_on,
# MAGIC   k.Modified_By AS modified_by,
# MAGIC   CAST(k.Modified_By_Delegate AS DOUBLE) AS modified_by_delegate,
# MAGIC   TRY_TO_TIMESTAMP(k.Modified_On) AS modified_on,
# MAGIC   k.Name AS usage_record_name,
# MAGIC   k.Owner AS owner,
# MAGIC   k.Owning_Business_Unit AS owning_business_unit,
# MAGIC   CAST(k.Record_Created_On AS DOUBLE) AS record_created_on,
# MAGIC   k.Status AS status,
# MAGIC   k.Status_Reason AS status_reason,
# MAGIC   CAST(k.Created_By_Delegate AS DOUBLE) AS created_by_delegate,
# MAGIC   k.Created_By AS created_by,
# MAGIC   CASE
# MAGIC     WHEN LOWER(k.Bot_Environment_Display_Name_PVA_Bot_PVA_Bot) LIKE '%prod%' THEN 'Production'
# MAGIC     WHEN LOWER(k.Bot_Environment_Display_Name_PVA_Bot_PVA_Bot) LIKE '%default%' THEN 'Default environment'
# MAGIC     ELSE 'Dev / Test / Other'
# MAGIC   END AS env_type
# MAGIC FROM ${pipeline_schema}.bot_usage_pp_coe_kit k
# MAGIC WHERE k.Do_Not_Modify_PVA_Bot_Usage IS NOT NULL;
