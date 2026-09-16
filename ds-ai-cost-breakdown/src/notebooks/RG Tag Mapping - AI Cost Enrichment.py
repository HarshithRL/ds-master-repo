# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # RG Tag Mapping & Enriched AI Cost View
# MAGIC
# MAGIC Views and tables, for quick loading of the dash: a bronze view over the prod source, the RG mapping view, and the enriched gold table read by the dashboard.

# COMMAND ----------

# CATALOG is passed by the job per bundle target (automation_d / _a / _p).
# The source is always the prod ingestion table, in every environment.
dbutils.widgets.text("CATALOG", "automation_d")
CATALOG = dbutils.widgets.get("CATALOG")
SOURCE_TABLE = "ingestion_azure_p.costs.azure_actual_cost"
BRONZE_VIEW = f"{CATALOG}.bronze.azure_actual_cost"
MAPPING_VIEW = f"{CATALOG}.gold.rg_tag_mapping_v"
GOLD_TABLE = f"{CATALOG}.gold.ai_foundry_costs_enriched"

# COMMAND ----------

for schema in ["bronze", "gold"]:
  spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")

def drop_if_table(full_name):
  """Earlier runs wrote tables with these names; CREATE OR REPLACE VIEW fails on a table, DROP TABLE fails on a view."""
  _, schema, name = full_name.split(".")
  if spark.sql(f"SHOW TABLES IN {CATALOG}.{schema} LIKE '{name}'").collect():
    if spark.sql(f"DESCRIBE TABLE EXTENDED {full_name}").filter("col_name = 'Type'").collect()[0]["data_type"] != "VIEW":
      spark.sql(f"DROP TABLE {full_name}")

def drop_if_view(full_name):
  """Gold used to be a view; CREATE OR REPLACE TABLE fails on an existing view."""
  _, schema, name = full_name.split(".")
  if spark.sql(f"SHOW TABLES IN {CATALOG}.{schema} LIKE '{name}'").collect():
    if spark.sql(f"DESCRIBE TABLE EXTENDED {full_name}").filter("col_name = 'Type'").collect()[0]["data_type"] == "VIEW":
      spark.sql(f"DROP VIEW {full_name}")

# The former intermediate (silver) view is folded into the gold view below.
spark.sql(f"DROP VIEW IF EXISTS {CATALOG}.gold.ai_costs_silver_v")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {MAPPING_VIEW} AS
SELECT * FROM VALUES
  ('%MDP-COGNITIVE-T-%', 'MDP Cognitive Services', 'Test', 'Etex Services N.V.', NULL, 'Cognitive services test'),
  ('%MDP-COGNITIVE-P-%', 'MDP Cognitive Services', 'Prod', 'Etex Services N.V.', NULL, 'Cognitive services production'),
  ('%MDP-COGNITIVE-D-%', 'MDP Cognitive Services', 'Dev', 'Etex Services N.V.', NULL, 'Cognitive services development'),
  ('%IA-ETEXMATE-D-%', 'Etex Mate', 'Dev', 'Etex Services N.V.', NULL, 'Etex Mate development'),
  ('%IA-ETEXMATE-P-%', 'Etex Mate', 'Prod', 'Etex Services N.V.', NULL, 'Etex Mate production'),
  ('%IA-ETEXMATE-T-%', 'Etex Mate', 'Test', 'Etex Services N.V.', NULL, 'Etex Mate test'),
  ('%DIGITAL-VAP-D-%', 'VAP', 'Dev', 'Etex Services N.V.', NULL, 'Voice AI Platform'),
  ('%DIGITAL-VAP-P-%', 'VAP', 'Prod', 'Etex Services N.V.', NULL, 'Voice AI Platform'),
  ('%DIGITAL-AISEARCH-D-%', 'AI Search', 'Dev', 'Etex Services N.V.', NULL, 'AI Search development'),
  ('%LOWCODE-COPILOT-D-%', 'Low Code Copilot', 'Dev', 'Etex Services N.V.', NULL, 'Copilot development'),
  ('%LOWCODE-COPILOT-P-%', 'Low Code Copilot', 'Prod', 'Etex Services N.V.', NULL, 'Copilot production'),
  ('%LOWCODE-COPILOT-T-%', 'Low Code Copilot', 'Test', 'Etex Services N.V.', NULL, 'Copilot test'),
  ('%COGNIZANT-GENAIBOT-D-%', 'Cognizant GenAI Bot', 'Dev', 'Etex Services N.V.', NULL, 'Cognizant GenAI Bot development'),
  ('%COGNIZANT-GENAIBOT-P-%', 'Cognizant GenAI Bot', 'Prod', 'Etex Services N.V.', NULL, 'Cognizant GenAI Bot production'),
  ('%COGNIZANT-GENAIBOT-T-%', 'Cognizant GenAI Bot', 'Test', 'Etex Services N.V.', NULL, 'Cognizant GenAI Bot test'),
  ('%COGNIZANT-VOICEAI-D-%', 'Cognizant Voice AI', 'Dev', 'Etex Services N.V.', NULL, 'Cognizant Voice AI development'),
  ('%COGNIZANT-VOICEAI-P-%', 'Cognizant Voice AI', 'Prod', 'Etex Services N.V.', NULL, 'Cognizant Voice AI production'),
  ('%COGNIZANT-VOICEAI-T-%', 'Cognizant Voice AI', 'Test', 'Etex Services N.V.', NULL, 'Cognizant Voice AI test'),
  ('%UIPATH-D-%', 'UiPath', 'Dev', 'Etex Services N.V.', NULL, 'UiPath development'),
  ('%UIPATH-P-%', 'UiPath', 'Prod', 'Etex Services N.V.', NULL, 'UiPath production'),
  ('%hub-citadel-p-%', 'Citadel', 'Prod', 'Etex Services N.V.', NULL, 'Citadel production'),
  ('rg-koen-playground', 'Sandbox', 'Dev', 'Etex Services N.V.', NULL, 'Personal playground')
AS t(
  rg_pattern,
  inferred_application,
  inferred_environment,
  inferred_company,
  inferred_owner,
  notes
)
""")

# COMMAND ----------

# Bronze is a pass-through view over the prod source (no copy).
drop_if_table(BRONZE_VIEW)
spark.sql(f"CREATE OR REPLACE VIEW {BRONZE_VIEW} AS SELECT * FROM {SOURCE_TABLE}")

# COMMAND ----------

drop_if_view(GOLD_TABLE)

spark.sql(f"""
CREATE OR REPLACE TABLE {GOLD_TABLE} AS
WITH tagged AS (
  SELECT
    a.*,
    UPPER(COALESCE(a.resourcegroupname, '')) AS rg_upper,
    LOWER(CONCAT_WS(' ',
      COALESCE(a.subscriptionname, ''),
      COALESCE(a.resourcegroupname, ''),
      COALESCE(a.consumedservice, ''),
      COALESCE(a.servicefamily, ''),
      COALESCE(a.metercategory, ''),
      COALESCE(a.metersubcategory, ''),
      COALESCE(a.metername, ''),
      COALESCE(a.productname, ''),
      COALESCE(a.additionalinfo, ''),
      COALESCE(a.serviceinfo1, ''),
      COALESCE(a.serviceinfo2, ''),
      COALESCE(a.tags, '')
    )) AS search_text,
    NULLIF(TRIM(get_json_object(a.tags, '$.Application')), '') AS tag_application,
    NULLIF(TRIM(get_json_object(a.tags, '$.Service')), '') AS raw_service,
    NULLIF(TRIM(get_json_object(a.tags, '$.Domain')), '') AS tag_domain,
    NULLIF(TRIM(get_json_object(a.tags, '$.deployment')), '') AS raw_deployment,
    NULLIF(TRIM(get_json_object(a.tags, '$.EnvironmentType')), '') AS raw_environment,
    NULLIF(TRIM(get_json_object(a.tags, '$.Company')), '') AS raw_company
  FROM {BRONZE_VIEW} a
),

source AS (
  SELECT
    t.*,
    CASE
      WHEN tag_application = 'EtexMate' THEN 'Etex Mate'
      WHEN tag_application IN ('GenAI-Chatbot', 'GenAi-ChatBot', 'GenAi-Chatbot') THEN 'GenAI-ChatBot'
      WHEN tag_application IN ('Uipath', 'UiPAth') THEN 'UiPath'
      ELSE tag_application
    END AS raw_application,
    CASE WHEN LOWER(tag_domain) = 'finance' THEN 'Finance' ELSE tag_domain END AS raw_domain
  FROM tagged t
),

mapped AS (
  SELECT
    s.*,
    m.rg_pattern,
    m.inferred_application,
    m.inferred_environment,
    m.inferred_company,
    m.inferred_owner
  FROM source s
  LEFT JOIN {MAPPING_VIEW} m
    ON s.rg_upper LIKE UPPER(m.rg_pattern)
),

derived AS (
  SELECT
    m.*,
    CASE
      WHEN search_text RLIKE 'github copilot|copilot studio|microsoft 365 copilot' THEN 'Copilot'
      WHEN search_text RLIKE 'qna maker|azure openai|foundry models|foundry tools|azure translator|defender for ai services' THEN 'AI Foundry / Azure AI'
      WHEN search_text RLIKE 'claude|anthropic|llama|mistral|gpt[- ]|embedding|inference' THEN 'Other model access'
      ELSE 'Non-AI or unclassified'
    END AS api_access,

    COALESCE(
      raw_application,
      inferred_application,
      CASE
        WHEN rg_upper RLIKE 'IA-ETEXMATE' THEN 'Etex Mate'
        WHEN rg_upper RLIKE 'COGNIZANT-GENAIBOT' THEN 'Cognizant GenAI Bot'
        WHEN rg_upper RLIKE 'LOWCODE-COPILOT' THEN 'Low Code Copilot'
        WHEN rg_upper RLIKE 'DIGITAL-AISEARCH' THEN 'AI Search'
        WHEN rg_upper RLIKE 'DIGITAL-VAP' THEN 'VAP'
        WHEN search_text RLIKE 'github copilot' THEN 'GitHub Copilot'
        WHEN search_text RLIKE 'copilot studio' THEN 'Copilot Studio'
        ELSE NULL
      END
    ) AS application,

    COALESCE(
      raw_service,
      CASE
        WHEN NULLIF(TRIM(consumedservice), '') IS NOT NULL THEN
          CASE UPPER(TRIM(consumedservice))
            WHEN 'MICROSOFT.APP' THEN 'Microsoft.App'
            WHEN 'MICROSOFT.CDN' THEN 'Microsoft.Cdn'
            WHEN 'MICROSOFT.COMPUTE' THEN 'Microsoft.Compute'
            WHEN 'MICROSOFT.CONTAINERREGISTRY' THEN 'Microsoft.ContainerRegistry'
            WHEN 'MICROSOFT.DATAFACTORY' THEN 'Microsoft.DataFactory'
            WHEN 'MICROSOFT.DBFORMYSQL' THEN 'Microsoft.DBforMySQL'
            WHEN 'MICROSOFT.DOCUMENTDB' THEN 'Microsoft.DocumentDb'
            WHEN 'MICROSOFT.HYBRIDCOMPUTE' THEN 'Microsoft.HybridCompute'
            WHEN 'MICROSOFT.INSIGHTS' THEN 'Microsoft.Insights'
            WHEN 'MICROSOFT.KEYVAULT' THEN 'Microsoft.KeyVault'
            WHEN 'MICROSOFT.MONITOR' THEN 'Microsoft.Monitor'
            WHEN 'MICROSOFT.NETWORK' THEN 'Microsoft.Network'
            WHEN 'MICROSOFT.SERVICEBUS' THEN 'Microsoft.ServiceBus'
            WHEN 'MICROSOFT.STORAGE' THEN 'Microsoft.Storage'
            WHEN 'MICROSOFT.SYNAPSE' THEN 'Microsoft.Synapse'
            WHEN 'MICROSOFT.WEB' THEN 'Microsoft.Web'
            ELSE TRIM(consumedservice)
          END
        ELSE NULL
      END,
      NULLIF(TRIM(servicefamily), ''),
      NULLIF(TRIM(metercategory), ''),
      'Unknown'
    ) AS service,

    COALESCE(
      raw_deployment,
      CASE
        WHEN metername RLIKE '(?i)gpt[- ]?[0-9]|claude|anthropic|llama|mistral' THEN metername
        WHEN productname RLIKE '(?i)gpt[- ]?[0-9]|claude|anthropic|llama|mistral' THEN productname
        WHEN search_text RLIKE '(?i)github copilot' THEN 'GitHub Copilot'
        WHEN search_text RLIKE '(?i)copilot studio' THEN 'Copilot Studio'
        ELSE NULL
      END
    ) AS model,

    COALESCE(
      raw_domain,
      CASE
        WHEN search_text RLIKE 'github copilot|copilot studio' THEN 'Intelligent Automation'
        WHEN rg_upper RLIKE 'SPOKE-IA' THEN 'Intelligent Automation'
        WHEN rg_upper RLIKE 'SPOKE-MDP' THEN 'Modern Data Platform'
        WHEN rg_upper RLIKE 'SPOKE-SAP' THEN 'SAP'
        WHEN rg_upper RLIKE 'SPOKE-DIGITAL' THEN 'Digital'
        WHEN rg_upper RLIKE 'SPOKE-LOWCODE' THEN 'Low Code'
        WHEN rg_upper RLIKE 'SPOKE-DMZ' THEN 'DMZ'
        WHEN rg_upper RLIKE 'SPOKE-DATA' THEN 'Secure Data'
        WHEN rg_upper RLIKE 'SPOKE-URSA' THEN 'URSA'
        WHEN rg_upper RLIKE 'SPOKE-APPS' THEN 'Apps'
        WHEN rg_upper RLIKE 'SPOKE-NEWWAYS' THEN 'New Ways'
        WHEN rg_upper RLIKE 'SPOKE-PLADUR' THEN 'Pladur Ecommerce'
        WHEN rg_upper RLIKE 'HUB-' THEN 'Shared Services'
        WHEN raw_domain RLIKE '(?i)^shared$|^shared services$' THEN 'Shared Services'
        WHEN raw_domain RLIKE '(?i)^foundation(s)?$' THEN 'Foundations'
        WHEN raw_domain RLIKE '(?i)^central functions$' THEN 'Central Functions'
        ELSE 'Unassigned'
      END
    ) AS spoke,

    CASE
      WHEN search_text RLIKE 'defender for ai services' THEN 'Defender for AI Services'
      WHEN metercategory RLIKE '(?i)azure openai' OR metersubcategory RLIKE '(?i)azure openai' OR metername RLIKE '(?i)azure openai' OR productname RLIKE '(?i)azure openai' THEN 'Azure OpenAI'
      WHEN search_text RLIKE 'azure translator' THEN 'Azure Translator'
      WHEN search_text RLIKE 'azure speech|voice live' THEN 'Azure Speech'
      WHEN search_text RLIKE 'azure document intelligence' THEN 'Azure Document Intelligence'
      WHEN search_text RLIKE 'azure custom vision' THEN 'Azure Custom Vision'
      WHEN search_text RLIKE 'azure vision' THEN 'Azure Vision'
      WHEN search_text RLIKE 'azure language' THEN 'Azure Language'
      WHEN search_text RLIKE 'qna maker' THEN 'QnA Maker'
      WHEN search_text RLIKE 'github copilot' THEN 'GitHub Copilot'
      WHEN search_text RLIKE 'copilot studio' THEN 'Copilot Studio'
      WHEN search_text RLIKE 'claude|anthropic' THEN 'Claude / Anthropic'
      WHEN search_text RLIKE 'llama' THEN 'Llama'
      WHEN search_text RLIKE 'mistral' THEN 'Mistral'
      ELSE NULL
    END AS ai_capability

  FROM mapped m
)

SELECT
  CAST(date AS DATE) AS cost_date,
  subscriptionname,
  subscriptionid,
  UPPER(resourcegroupname) AS resourcegroupname,
  resourceid,
  consumedservice,
  servicefamily,
  metercategory,
  metersubcategory,
  metername,
  productname,
  pricingcurrency,
  billingcurrency,
  costinpricingcurrency,
  costinbillingcurrency,
  CASE
    WHEN UPPER(billingcurrency) = 'EUR' THEN costinbillingcurrency
    WHEN UPPER(pricingcurrency) = 'EUR' THEN costinpricingcurrency
    ELSE NULL
  END AS cost_eur,
  costinusd AS cost_usd,
  paygcostinbillingcurrency,
  paygcostinusd,
  quantity,
  tags,
  application,
  service,
  model,
  spoke,
  api_access,
  ai_capability,
  COALESCE(inferred_environment, raw_environment) AS environment,
  COALESCE(inferred_company, raw_company) AS company,
  CASE
    WHEN rg_pattern IS NOT NULL AND raw_application IS NULL THEN TRUE
    ELSE FALSE
  END AS application_inferred,
  CASE
    WHEN rg_pattern IS NOT NULL AND raw_domain IS NULL THEN TRUE
    ELSE FALSE
  END AS spoke_inferred,
  CASE
    WHEN model IS NOT NULL AND raw_deployment IS NULL THEN TRUE
    ELSE FALSE
  END AS model_inferred,
  batch_id,
  load_ts
FROM derived
""")
