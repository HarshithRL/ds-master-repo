# Databricks notebook source
import re


dbutils.widgets.text("catalog", "automation_d")
dbutils.widgets.text("source_table", "ingestion_azure_p.costs.azure_actual_cost")
dbutils.widgets.text("write_gold", "false")

CATALOG = dbutils.widgets.get("catalog").strip()
SOURCE_TABLE = dbutils.widgets.get("source_table").strip()
WRITE_GOLD = dbutils.widgets.get("write_gold").strip().lower() == "true"

if not re.fullmatch(r"[a-z][a-z0-9_]*", CATALOG):
    raise ValueError(f"Invalid catalog name: {CATALOG!r}")

if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", SOURCE_TABLE):
    raise ValueError(f"Invalid source table name: {SOURCE_TABLE!r}")

if not WRITE_GOLD:
    raise RuntimeError("Gold refresh is disabled for this target.")

BRONZE_VIEW = f"{CATALOG}.bronze.azure_actual_cost"
MAPPING_VIEW = f"{CATALOG}.gold.rg_tag_mapping_v"
GOLD_TABLE = f"{CATALOG}.gold.ai_foundry_costs_enriched"


def relation_type(full_name):
    if not spark.catalog.tableExists(full_name):
        return None
    return spark.catalog.getTable(full_name).tableType


for schema in ("bronze", "gold"):
    spark.sql(f"DESCRIBE SCHEMA {CATALOG}.{schema}")

source_columns = {field.name.lower() for field in spark.table(SOURCE_TABLE).schema.fields}


def optional_source_column(column_name, data_type):
  if column_name.lower() in source_columns:
    return column_name
  return f"CAST(NULL AS {data_type})"


BATCH_ID_COLUMN = optional_source_column("batch_id", "STRING")
LOAD_TS_COLUMN = optional_source_column("load_ts", "TIMESTAMP")

for relation in (BRONZE_VIEW, MAPPING_VIEW):
    existing_type = relation_type(relation)
    if existing_type not in (None, "VIEW"):
        raise RuntimeError(f"Expected {relation} to be a view, found {existing_type}.")

existing_gold_type = relation_type(GOLD_TABLE)
if existing_gold_type not in (None, "MANAGED", "EXTERNAL"):
    raise RuntimeError(f"Expected {GOLD_TABLE} to be a table, found {existing_gold_type}.")

spark.sql(
    f"""
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
    AS mapping(
      rg_pattern,
      inferred_application,
      inferred_environment,
      inferred_company,
      inferred_owner,
      notes
    )
    """
)

spark.sql(f"CREATE OR REPLACE VIEW {BRONZE_VIEW} AS SELECT * FROM {SOURCE_TABLE}")

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {GOLD_TABLE} AS
    WITH tagged AS (
      SELECT
        cost.*,
        UPPER(COALESCE(cost.resourcegroupname, '')) AS rg_upper,
        LOWER(CONCAT_WS(' ',
          COALESCE(cost.subscriptionname, ''),
          COALESCE(cost.resourcegroupname, ''),
          COALESCE(cost.resourceid, ''),
          COALESCE(cost.consumedservice, ''),
          COALESCE(cost.servicefamily, ''),
          COALESCE(cost.metercategory, ''),
          COALESCE(cost.metersubcategory, ''),
          COALESCE(cost.metername, ''),
          COALESCE(cost.productname, ''),
          COALESCE(cost.additionalinfo, ''),
          COALESCE(cost.serviceinfo1, ''),
          COALESCE(cost.serviceinfo2, ''),
          COALESCE(cost.tags, '')
        )) AS search_text,
        NULLIF(TRIM(get_json_object(cost.tags, '$.Application')), '') AS tag_application,
        NULLIF(TRIM(get_json_object(cost.tags, '$.Service')), '') AS raw_service,
        NULLIF(TRIM(get_json_object(cost.tags, '$.Domain')), '') AS tag_domain,
        NULLIF(TRIM(get_json_object(cost.tags, '$.deployment')), '') AS raw_deployment,
        NULLIF(TRIM(get_json_object(cost.tags, '$.EnvironmentType')), '') AS raw_environment,
        NULLIF(TRIM(get_json_object(cost.tags, '$.Company')), '') AS raw_company,
        NULLIF(LOWER(REGEXP_EXTRACT(cost.resourceid, '(?i)/providers/([^/]+/[^/]+)', 1)), '') AS resource_type,
        COALESCE(
          NULLIF(REGEXP_EXTRACT(cost.resourceid, '/([^/]+)$', 1), ''),
          NULLIF(cost.resourcegroupname, ''),
          NULLIF(cost.productname, ''),
          NULLIF(cost.metername, ''),
          'Unassigned'
        ) AS resource_name,
        COALESCE(
          NULLIF(cost.resourcelocation, ''),
          NULLIF(cost.location, ''),
          NULLIF(cost.meterregion, '')
        ) AS azure_region
      FROM {BRONZE_VIEW} cost
    ),
    source AS (
      SELECT
        tagged.*,
        CASE
          WHEN tag_application = 'EtexMate' THEN 'Etex Mate'
          WHEN tag_application IN ('GenAI-Chatbot', 'GenAi-ChatBot', 'GenAi-Chatbot') THEN 'GenAI-ChatBot'
          WHEN tag_application IN ('Uipath', 'UiPAth') THEN 'UiPath'
          ELSE tag_application
        END AS raw_application,
        CASE WHEN LOWER(tag_domain) = 'finance' THEN 'Finance' ELSE tag_domain END AS raw_domain
      FROM tagged
    ),
    mapped AS (
      SELECT
        source.*,
        mapping.rg_pattern,
        mapping.inferred_application,
        mapping.inferred_environment,
        mapping.inferred_company,
        mapping.inferred_owner
      FROM source
      LEFT JOIN {MAPPING_VIEW} mapping
        ON source.rg_upper LIKE UPPER(mapping.rg_pattern)
    ),
    enriched AS (
      SELECT
        mapped.*,
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
          END
        ) AS application,
        COALESCE(
          raw_service,
          CASE UPPER(NULLIF(TRIM(consumedservice), ''))
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
            ELSE NULLIF(TRIM(consumedservice), '')
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
            WHEN search_text RLIKE 'github copilot' THEN 'GitHub Copilot'
            WHEN search_text RLIKE 'copilot studio' THEN 'Copilot Studio'
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
        END AS ai_capability
      FROM mapped
    ),
    classified AS (
      SELECT
        enriched.*,
        CASE
          WHEN search_text RLIKE 'github copilot|copilot studio|microsoft 365 copilot' THEN 'Copilot'
          WHEN search_text RLIKE 'azure openai|foundry|azure translator|azure speech|azure document intelligence|azure custom vision|azure vision|azure language|qna maker|defender for ai services|claude|anthropic|llama|mistral|gpt[- ]|embedding|machine learning' THEN 'AI Foundry'
          WHEN resource_type RLIKE '^microsoft\\.databricks/' OR search_text RLIKE 'databricks' THEN 'Databricks'
          ELSE 'Infrastructure'
        END AS cost_domain,
        CASE
          WHEN search_text RLIKE 'github copilot|copilot studio|microsoft 365 copilot' THEN TRUE
          WHEN search_text RLIKE 'azure openai|foundry|azure translator|azure speech|azure document intelligence|azure custom vision|azure vision|azure language|qna maker|defender for ai services|claude|anthropic|llama|mistral|gpt[- ]|embedding|machine learning|realtime inferencing|model serving' THEN TRUE
          ELSE FALSE
        END AS is_ai
      FROM enriched
    )
    SELECT
      CAST(date AS DATE) AS cost_date,
      subscriptionname,
      subscriptionid,
      UPPER(resourcegroupname) AS resourcegroupname,
      resourceid,
      resource_name,
      resource_type,
      azure_region,
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
      END AS cost_eur,
      costinusd AS cost_usd,
      paygcostinbillingcurrency,
      paygcostinusd,
      quantity,
      tags,
      cost_domain,
      CASE
        WHEN cost_domain = 'Copilot' THEN 'Copilot'
        WHEN cost_domain = 'AI Foundry' THEN 'AI Services'
        WHEN search_text RLIKE 'reservation|savings plan' THEN 'Reservations & Savings Plans'
        WHEN chargetype RLIKE '(?i)credit|adjustment' OR search_text RLIKE 'credit|adjustment' THEN 'Credits & Adjustments'
        WHEN search_text RLIKE 'defender|sentinel|security|key vault' THEN 'Security'
        WHEN search_text RLIKE 'backup|recovery services|site recovery|restore point' THEN 'Backup & DR'
        WHEN search_text RLIKE 'storage|disk|blob|file share|snapshot' THEN 'Storage & Disks'
        WHEN search_text RLIKE 'sql database|managed instance|mysql|postgres|redis|cosmos|documentdb|database' THEN 'Databases'
        WHEN search_text RLIKE 'network|gateway|expressroute|private link|load balancer|cdn' THEN 'Networking'
        WHEN search_text RLIKE 'data factory|datafactory|databricks|fabric|synapse|analytics|purview' THEN 'Data & Analytics'
        WHEN search_text RLIKE 'devops|visual studio|service bus|event hub|api management|integration' THEN 'Integration & DevOps'
        WHEN search_text RLIKE 'monitor|log analytics|insights' THEN 'Monitoring & Management'
        WHEN search_text RLIKE 'saas|support|licence|license|github' THEN 'SaaS, Support & Licences'
        ELSE 'Compute'
      END AS service_category,
      is_ai,
      application,
      service,
      model,
      spoke,
      ai_capability,
      COALESCE(inferred_environment, raw_environment) AS environment,
      COALESCE(inferred_company, raw_company) AS company,
      CASE WHEN rg_pattern IS NOT NULL AND raw_application IS NULL THEN TRUE ELSE FALSE END AS application_inferred,
      CASE WHEN rg_pattern IS NOT NULL AND raw_domain IS NULL THEN TRUE ELSE FALSE END AS spoke_inferred,
      CASE WHEN model IS NOT NULL AND raw_deployment IS NULL THEN TRUE ELSE FALSE END AS model_inferred,
      {BATCH_ID_COLUMN} AS batch_id,
      {LOAD_TS_COLUMN} AS load_ts
    FROM classified
    """
)
