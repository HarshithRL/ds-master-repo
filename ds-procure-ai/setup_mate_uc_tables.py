# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # Setup Mate UC Tables
# MAGIC
# MAGIC Creates the 24 `mate_*` Delta tables (+ volume) in `{catalog}.bronze` for the
# MAGIC ds-procure-ai app. Run this in each environment **before** the consumer access
# MAGIC pipeline so that GRANT statements don't fail on non-existent objects.
# MAGIC
# MAGIC | Environment | Catalog        |
# MAGIC |------------|----------------|
# MAGIC | DEV / TEST | `automation_d` |
# MAGIC | ACC        | `automation_a` |
# MAGIC | PRD        | `automation_p` |
# MAGIC
# MAGIC The job passes `catalog` as a parameter; for manual runs use the widget.

# COMMAND ----------

# DBTITLE 1,Cell 2
dbutils.widgets.text("catalog", "automation_d", "Unity Catalog name")
catalog = dbutils.widgets.get("catalog").strip()
schema = "bronze"
volume = "bronze_volume"

print(f"Target: {catalog}.{schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Volume

# COMMAND ----------

spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}")
print(f"✓ Volume {catalog}.{schema}.{volume}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Tables

# COMMAND ----------

tables = {
    "mate_hub_module": """
        id STRING NOT NULL, name STRING NOT NULL, description STRING, icon STRING,
        path STRING NOT NULL, category STRING NOT NULL, sort_order INT NOT NULL, enabled INT NOT NULL
    """,
    "mate_app_user": """
        workspace_id STRING NOT NULL, user_name STRING, display_name STRING, email STRING,
        created_at STRING NOT NULL, updated_at STRING NOT NULL
    """,
    "mate_user_module": """
        workspace_id STRING NOT NULL, module_id STRING NOT NULL, granted_at STRING NOT NULL
    """,
    "mate_project": """
        id STRING NOT NULL, code STRING NOT NULL, owner_id STRING NOT NULL, module_id STRING NOT NULL,
        name STRING NOT NULL, workflow_entry_point STRING, business_process STRING, requester STRING,
        dept STRING, category STRING, region STRING, status STRING NOT NULL, priority STRING NOT NULL,
        budget STRING, award_horizon STRING, description STRING, progress INT NOT NULL, deadline STRING,
        requirements_json STRING, created_at STRING NOT NULL, updated_at STRING NOT NULL
    """,
    "mate_artifact": """
        id STRING NOT NULL, project_id STRING NOT NULL, uploaded_by STRING NOT NULL, kind STRING NOT NULL,
        folder STRING, original_name STRING NOT NULL, content_type STRING, size_bytes INT,
        storage_relpath STRING NOT NULL, parsed_json STRING, parse_status STRING, parse_error STRING,
        parsed_relpath STRING, vendor_id STRING, doc_role STRING, role_confidence DOUBLE,
        content_hash STRING, superseded_by STRING, created_at STRING NOT NULL
    """,
    "mate_chunk": """
        id STRING NOT NULL, project_id STRING NOT NULL, artifact_id STRING NOT NULL, ordinal INT NOT NULL,
        chunk_type STRING NOT NULL, text STRING NOT NULL, token_count INT NOT NULL,
        heading_path_json STRING, block_ids_json STRING, location_json STRING, table_json STRING,
        page_kind STRING, reconstructor STRING, created_at STRING NOT NULL
    """,
    "mate_chunk_embedding": """
        chunk_id STRING NOT NULL, project_id STRING NOT NULL, vendor_id STRING,
        doc_role STRING, chunk_type STRING, embedding STRING NOT NULL,
        model_version STRING NOT NULL
    """,
    "mate_vendor": """
        id STRING NOT NULL, project_id STRING NOT NULL, name STRING NOT NULL, legal_entity STRING,
        registry_id STRING, status STRING, created_at STRING NOT NULL
    """,
    "mate_requirement": """
        id STRING NOT NULL, project_id STRING NOT NULL, ordinal INT NOT NULL, section STRING,
        text STRING NOT NULL, category STRING, weight DOUBLE, mandatory INT NOT NULL,
        source_artifact_id STRING, source_page INT, created_at STRING NOT NULL
    """,
    "mate_evidence": """
        id STRING NOT NULL, project_id STRING NOT NULL, requirement_id STRING NOT NULL,
        vendor_id STRING NOT NULL, status STRING NOT NULL, claim_text STRING, artifact_id STRING,
        chunk_id STRING, page INT, confidence DOUBLE, model_version STRING NOT NULL,
        prompt_version STRING NOT NULL, extracted_at STRING NOT NULL, reviewed_by STRING, reviewed_at STRING
    """,
    "mate_pricing_line": """
        id STRING NOT NULL, project_id STRING, vendor_id STRING, offer_type STRING NOT NULL,
        role STRING, seniority STRING, rate DECIMAL(38,10), rate_unit STRING, currency STRING,
        quantity DECIMAL(38,10), line_total DECIMAL(38,10), etex_effort_days DECIMAL(38,10),
        etex_effort_side STRING, discount_terms STRING, annexe_a02_completed INT, artifact_id STRING,
        page INT, chunk_id STRING, verified INT NOT NULL, model_version STRING NOT NULL
    """,
    "mate_bid_profile": """
        id STRING NOT NULL, project_id STRING NOT NULL, vendor_id STRING NOT NULL,
        facts_json STRING NOT NULL, model_version STRING NOT NULL, extracted_at STRING NOT NULL
    """,
    "mate_kb_node": """
        id STRING NOT NULL, project_id STRING NOT NULL, type STRING NOT NULL, label STRING NOT NULL,
        props STRING, source_artifact_id STRING, source_page INT, confidence DOUBLE, model_version STRING
    """,
    "mate_kb_edge": """
        id STRING NOT NULL, project_id STRING NOT NULL, src STRING NOT NULL, dst STRING NOT NULL,
        type STRING NOT NULL, props STRING, source_artifact_id STRING, source_page INT,
        confidence DOUBLE, model_version STRING
    """,
    "mate_chat_session": """
        id STRING NOT NULL, project_id STRING NOT NULL, title STRING NOT NULL,
        created_at STRING NOT NULL, updated_at STRING NOT NULL
    """,
    "mate_chat_message": """
        id STRING NOT NULL, session_id STRING NOT NULL, role STRING NOT NULL,
        text STRING NOT NULL, created_at STRING NOT NULL
    """,
    "mate_ontology_requirement": """
        id STRING NOT NULL, project_id STRING NOT NULL, req_id STRING NOT NULL,
        text STRING NOT NULL, category STRING NOT NULL, target STRING,
        mandatory INT NOT NULL, weight DOUBLE, ontology_version STRING NOT NULL
    """,
    "mate_ontology_offering": """
        id STRING NOT NULL, project_id STRING NOT NULL, vendor_id STRING NOT NULL,
        req_id STRING NOT NULL, status STRING NOT NULL, value_text STRING NOT NULL,
        numeric_value DOUBLE, locator STRING NOT NULL, quote STRING NOT NULL,
        chunk_id STRING, confidence DOUBLE
    """,
    "mate_tco_line": """
        id STRING NOT NULL, project_id STRING NOT NULL, vendor_id STRING NOT NULL,
        year INT NOT NULL, line_type STRING NOT NULL, amount_eur DOUBLE, mandays DOUBLE,
        rate_eur_per_day DOUBLE, derived INT NOT NULL, locator STRING NOT NULL, note STRING
    """,
    "mate_ontology_flag": """
        id STRING NOT NULL, project_id STRING NOT NULL, severity STRING NOT NULL,
        text STRING NOT NULL, vendors_json STRING NOT NULL, locator STRING
    """,
    "mate_pack": """
        id STRING NOT NULL, project_id STRING NOT NULL, kind STRING NOT NULL,
        status STRING NOT NULL, path STRING, created_at STRING NOT NULL
    """,
    "mate_quality_flag": """
        id STRING NOT NULL, project_id STRING, artifact_id STRING, kind STRING NOT NULL,
        detail STRING, severity STRING, created_at STRING NOT NULL
    """,
    # Analyst decision log. bid_id NULL = project-level note.
    "mate_note": """
        id STRING NOT NULL, project_id STRING NOT NULL, bid_id STRING, body STRING NOT NULL,
        kind STRING NOT NULL, source STRING NOT NULL, author STRING,
        created_at STRING NOT NULL, updated_at STRING NOT NULL
    """,
    # Durable kb_build run record. heartbeat_at is what distinguishes a dead
    # build from a slow one; without this table stalled builds are never reaped.
    "mate_kb_build_job": """
        id STRING NOT NULL, project_id STRING NOT NULL, status STRING NOT NULL,
        mode STRING NOT NULL, run_id STRING, message STRING, error STRING,
        attempt INT NOT NULL, heartbeat_at STRING, started_at STRING,
        finished_at STRING, created_at STRING NOT NULL, updated_at STRING NOT NULL
    """,
}

created = 0
for table_name, columns in tables.items():
    fqn = f"{catalog}.{schema}.{table_name}"
    ddl = f"CREATE TABLE IF NOT EXISTS {fqn} ({columns})"
    spark.sql(ddl)
    created += 1
    print(f"✓ [{created}/{len(tables)}] {table_name}")

print(f"\nDone: {created} tables created/verified in {catalog}.{schema}")

# COMMAND ----------

# DBTITLE 1,Seed Hub Modules
# MAGIC %md
# MAGIC ## Seed Hub Modules
# MAGIC Pre-populate the 6 hub modules so the Nexus homepage shows them at first boot.

# COMMAND ----------

# DBTITLE 1,Seed hub module rows
hub_table = f"{catalog}.{schema}.mate_hub_module"
modules = [
    ("procurement-ai-assistant", "Procurement AI Assistant", "Ask questions, generate insights, and receive AI-powered support to enhance your work.", "/assets/icon-chat.svg", "/app/procurement-ai-assistant", "General", 1, 1),
    ("document-builder", "Document Builder", "Create, merge and edit documents or code instantly with AI-driven precision.", "/assets/icon-document.svg", "/app/document-builder", "General", 2, 0),
    ("document-translator", "Document Translator", "Translate texts and document files while preserving the format.", "/assets/icon-translate.svg", "/app/document-translator", "General", 3, 0),
    ("scope-builder", "Scope Builder", "Transform raw requirements into actionable user stories.", "/assets/icon-scope.svg", "/app/scope-builder", "General", 4, 0),
    ("accounting", "Accounting Assistant", "Ask questions and find answers from the Group Accounting Manual.", "/assets/icon-accounting.svg", "/app/accounting", "Group Accounting Manual", 5, 0),
    ("policy-search", "Policy Search", "Search accounting policies and guidelines using AI.", "/assets/icon-search.svg", "/app/policy-search", "Group Accounting Manual", 6, 0),
]
for m in modules:
    mid, name, desc, icon, mpath, cat, sort_order, enabled = m
    spark.sql(f"""
        MERGE INTO {hub_table} AS t
        USING (SELECT '{mid}' AS id) AS s ON t.id = s.id
        WHEN NOT MATCHED THEN INSERT (id, name, description, icon, path, category, sort_order, enabled)
        VALUES ('{mid}', '{name}', '{desc}', '{icon}', '{mpath}', '{cat}', {sort_order}, {enabled})
    """)
print(f"Seeded {len(modules)} hub modules into {hub_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify

# COMMAND ----------

df = spark.sql(f"SHOW TABLES IN {catalog}.{schema} LIKE 'mate_*'")
print(f"Found {df.count()} mate_* tables:")
df.select("tableName").orderBy("tableName").show(30, truncate=False)
