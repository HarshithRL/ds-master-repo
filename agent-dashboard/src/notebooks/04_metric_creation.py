# Databricks notebook source
# MAGIC %run ./config_file

# COMMAND ----------

# MAGIC %python
# MAGIC spark.sql(f"USE CATALOG {UNITY_CATALOG}")
# MAGIC print(f"Active catalog: {UNITY_CATALOG}")

# COMMAND ----------
# DBTITLE 1,Dashboard
# =============================================================================
# METRIC VIEW : copilot_analytics_metrics
# CATALOG     : cdigitpoc.abs
# PURPOSE     : Unified semantic layer for all KPIs (01-12, 14-17).
# DIMENSIONS  : 12 (interaction_type, license_type, uses_bing_search,
#               model_provider, region, interaction_date, user_email,
#               agent_name, target_agent_id, env_id, env_name, app_host)
# MEASURES    : 29
#   KPI 01-12, 14-15  : scalar measures (no grouping needed)
#   KPI 16 grouped    : Interactions by Region (GROUP BY Region dimension)
#   KPI 17 grouped    : Avg Interactions per User by Region (GROUP BY Region)
#   KPI 16 per-region : NorthWest/South/LatAm/East/APAC/Africa Interactions
#   KPI 17 per-region : NorthWest/South/LatAm/East/APAC/Africa Avg per User
#   (per-region measures are scorecard-ready - no GROUP BY needed in dashboard)
# JOIN        : silver_dim_environment via env_id (LEFT JOIN, many-to-one)
# KPI 13 excluded - target_agent_id does not reliably match silver_dim_agent
# =============================================================================

TARGET = SILVER

yaml_sql = f"""
CREATE OR REPLACE VIEW {TARGET}.copilot_analytics_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: {TARGET}.silver_fact_interactions
  comment: Etex M365 Copilot - 29 measures covering KPI 01-17.

  joins:
    - name: dim_env
      source: {TARGET}.silver_dim_environment
      on: source.env_id = dim_env.environment_id
      cardinality: many_to_one
      rely:
        at_most_one_match: true

  dimensions:
    - name: Interaction Type
      expr: interaction_type
      display_name: Interaction Type
      synonyms: [agent type, copilot type, channel]
    - name: License Type
      expr: license_type
      display_name: License Type
      synonyms: [license, subscription, tier]
    - name: Uses Bing Search
      expr: uses_bing_search
      display_name: Used Bing Search
    - name: Model Provider
      expr: model_provider
      display_name: AI Model Provider
      synonyms: [model, openai, llm]
    - name: Region
      expr: admin_unit_name
      display_name: Region
      comment: 6 values - NorthWest, South, LatAm, East, APAC, Africa. NULL for 551 rows.
      synonyms: [admin unit, geography, location, area]
    - name: Interaction Date
      expr: creation_date
      display_name: Interaction Date
      synonyms: [date, day, when]
    - name: User Email
      expr: user_email
      display_name: User
      synonyms: [user, employee, person]
    - name: Agent Name
      expr: agent_name
      display_name: Agent Name
      synonyms: [agent, bot, copilot agent]
    - name: Target Agent ID
      expr: target_agent_id
      display_name: Declarative Agent ID
      synonyms: [agent id, guid]
    - name: Environment ID
      expr: env_id
      display_name: Environment ID
    - name: Environment Name
      expr: dim_env.environment_name
      display_name: Environment Name
      synonyms: [environment, power platform, pp env]
    - name: App Host
      expr: app_host
      display_name: App Host
      synonyms: [app, application, host]

  measures:
    - name: Total Interactions
      expr: COUNT(1)
      display_name: Total Interactions
      comment: KPI 01 - Total M365 Copilot interaction events.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
      synonyms: [interactions, total, events]
    - name: Unique Active Users
      expr: COUNT(DISTINCT user_email)
      display_name: Unique Active Users
      comment: KPI 02 - Distinct employees who used Copilot.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
      synonyms: [users, active users, distinct users]
    - name: Avg Interactions per User
      expr: MEASURE(`Total Interactions`) / MEASURE(`Unique Active Users`)
      display_name: Avg Interactions per User
      comment: KPI 03 - Global avg interactions per active user.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: Bing Interactions
      expr: COUNT(1) FILTER (WHERE uses_bing_search = TRUE)
      display_name: Bing Search Interactions
      comment: KPI 04 - Interactions where Bing plugin was invoked.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Pct Using Bing
      expr: MEASURE(`Bing Interactions`) * 100.0 / MEASURE(`Total Interactions`)
      display_name: Pct Using Bing Search
      comment: KPI 05 - 0 to 100 scale.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: OpenAI Interactions
      expr: COUNT(1) FILTER (WHERE model_provider = 'OpenAI')
      display_name: OpenAI Model Interactions
      comment: KPI 06
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Premium Interactions
      expr: COUNT(1) FILTER (WHERE license_type = 'Premium')
      display_name: Premium License Interactions
      comment: KPI 07
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Starter Interactions
      expr: COUNT(1) FILTER (WHERE license_type = 'Starter')
      display_name: Starter License Interactions
      comment: KPI 08
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Premium Share
      expr: MEASURE(`Premium Interactions`) * 100.0 / MEASURE(`Total Interactions`)
      display_name: Premium Share Pct
      comment: KPI 09 - 0 to 100 scale.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: Declarative Interactions
      expr: COUNT(1) FILTER (WHERE interaction_type = 'Declarative')
      display_name: Declarative Agent Interactions
      comment: KPI 10
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Custom Engine Interactions
      expr: COUNT(1) FILTER (WHERE interaction_type = 'CustomEngine')
      display_name: Custom Engine Agent Interactions
      comment: KPI 11
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: BizChat M365 Interactions
      expr: COUNT(1) FILTER (WHERE interaction_type = 'BizChat_M365')
      display_name: Native M365 Copilot Interactions
      comment: KPI 12
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Unique Environments
      expr: COUNT(DISTINCT env_id) FILTER (WHERE env_id IS NOT NULL AND env_id != '')
      display_name: Unique Environments Touched
      comment: >-
        KPI 14 - Count of distinct Power Platform environments where at least
        one CustomEngine interaction occurred. Counted from fact table env_id
        (not from dim catalog) so all 7 active environments are included even
        if 3 are unmatched in silver_dim_environment. Both IS NOT NULL and
        != '' filters required because env_id is stored as empty string
        for BizChat_M365, Declarative, and MicrosoftAgent rows.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
      synonyms: [environments, unique environments, power platform environments, pp env count, kpi 14]
    - name: Unique Regions
      expr: COUNT(DISTINCT admin_unit_name) FILTER (WHERE admin_unit_name IS NOT NULL)
      display_name: Unique Regions Active
      comment: KPI 15
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Interactions by Region
      expr: COUNT(1) FILTER (WHERE admin_unit_name IS NOT NULL)
      display_name: Interactions by Region
      comment: KPI 16 grouped - use with Region dimension for bar chart or table.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
      synonyms: [interactions per region, regional interactions, kpi 16]
    - name: Active Users by Region
      expr: COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name IS NOT NULL)
      display_name: Active Users by Region
      comment: KPI 17 component - use with Region dimension.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Avg Interactions per User by Region
      expr: MEASURE(`Interactions by Region`) / MEASURE(`Active Users by Region`)
      display_name: Avg Interactions per User by Region
      comment: KPI 17 grouped - use with Region dimension for bar chart or table.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
      synonyms: [avg per user per region, regional avg, kpi 17]
    - name: NorthWest Interactions
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-NorthWest')
      display_name: NorthWest - Interactions
      comment: KPI 16 NorthWest - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: South Interactions
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-South')
      display_name: South - Interactions
      comment: KPI 16 South - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: LatAm Interactions
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-LatAm')
      display_name: LatAm - Interactions
      comment: KPI 16 LatAm - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: East Interactions
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-East')
      display_name: East - Interactions
      comment: KPI 16 East - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: APAC Interactions
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-APAC')
      display_name: APAC - Interactions
      comment: KPI 16 APAC - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: Africa Interactions
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-Africa')
      display_name: Africa - Interactions
      comment: KPI 16 Africa - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 0
    - name: NorthWest Avg per User
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-NorthWest') / COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-NorthWest')
      display_name: NorthWest - Avg per User
      comment: KPI 17 NorthWest - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: South Avg per User
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-South') / COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-South')
      display_name: South - Avg per User
      comment: KPI 17 South - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: LatAm Avg per User
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-LatAm') / COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-LatAm')
      display_name: LatAm - Avg per User
      comment: KPI 17 LatAm - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: East Avg per User
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-East') / COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-East')
      display_name: East - Avg per User
      comment: KPI 17 East - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: APAC Avg per User
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-APAC') / COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-APAC')
      display_name: APAC - Avg per User
      comment: KPI 17 APAC - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
    - name: Africa Avg per User
      expr: COUNT(1) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-Africa') / COUNT(DISTINCT user_email) FILTER (WHERE admin_unit_name = 'ETEX-AU-REG-Africa')
      display_name: Africa - Avg per User
      comment: KPI 17 Africa - scorecard ready, no GROUP BY needed.
      format:
        type: number
        decimal_places:
          type: exact
          places: 2
$$
"""

spark.sql(yaml_sql)
print("Done -> cdigitpoc.abs.copilot_analytics_metrics created (29 measures)")