-- Databricks notebook source
-- MAGIC %run ./config_file

-- COMMAND ----------

-- MAGIC %python
-- MAGIC spark.sql(f"USE CATALOG {UNITY_CATALOG}")
-- MAGIC print(f"Active catalog: {UNITY_CATALOG}")

-- COMMAND ----------
-- DBTITLE 1,Metric View - Bot Usage
-- Unity Catalog METRIC VIEW  ·  Bot Usage & Adoption
-- Source: silver.bot_usage  (one row per bot per day)
-- Run THIS statement by itself (it is a single CREATE statement).

CREATE OR REPLACE VIEW silver.bot_usage_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Copilot Studio bot usage & adoption KPIs. Recency windows are anchored on the latest usage_date in the source, matching the Lakeview dashboard."

source: |
  SELECT
    b.bot_name,
    b.usage_date,
    b.environment,
    b.conversations,
    r.max_dt,
    r.current_month
  FROM silver.bot_usage AS b
  CROSS JOIN (
    SELECT
      MAX(usage_date)                       AS max_dt,
      DATE_TRUNC('MONTH', MAX(usage_date))  AS current_month
    FROM silver.bot_usage
  ) AS r

dimensions:
  - name: Bot Name
    expr: source.bot_name

  - name: Environment
    expr: source.environment

  - name: Environment Type
    expr: >
      CASE
        WHEN source.environment LIKE '%PROD%'           THEN 'Production'
        WHEN LOWER(source.environment) LIKE '%default%' THEN 'Default environment'
        ELSE 'Dev / Test / Other'
      END

  - name: Usage Date
    expr: source.usage_date

  - name: Usage Month
    expr: DATE_TRUNC('MONTH', source.usage_date)

  - name: Usage Quarter
    expr: DATE_TRUNC('QUARTER', source.usage_date)

  - name: Usage Month Label
    expr: DATE_FORMAT(DATE_TRUNC('MONTH', source.usage_date), 'MMM yyyy')

  - name: Is Current Partial Month
    expr: CASE WHEN DATE_TRUNC('MONTH', source.usage_date) = source.current_month THEN true ELSE false END

measures:
  - name: total_conversations
    expr: SUM(source.conversations)

  - name: total_agents
    expr: COUNT(DISTINCT source.bot_name)

  - name: total_environments
    expr: COUNT(DISTINCT source.environment)

  - name: active_days
    expr: COUNT(DISTINCT source.usage_date)

  - name: avg_conversations_per_bot_day
    expr: ROUND(AVG(source.conversations), 2)

  - name: active_agents_30d
    expr: COUNT(DISTINCT CASE WHEN source.usage_date >= DATE_SUB(source.max_dt, 30) THEN source.bot_name END)

  - name: active_agents_60d
    expr: COUNT(DISTINCT CASE WHEN source.usage_date >= DATE_SUB(source.max_dt, 60) THEN source.bot_name END)

  - name: pct_active_agents
    expr: >
      ROUND(
        COUNT(DISTINCT CASE WHEN source.usage_date >= DATE_SUB(source.max_dt, 30) THEN source.bot_name END) * 100.0
        / NULLIF(COUNT(DISTINCT source.bot_name), 0)
      , 1)

  - name: first_used
    expr: MIN(source.usage_date)

  - name: last_used
    expr: MAX(source.usage_date)

  - name: days_since_last_use
    expr: DATEDIFF(MAX(source.max_dt), MAX(source.usage_date))

  - name: latest_data_date
    expr: MAX(source.max_dt)
$$;