# Databricks notebook source


# COMMAND ----------

# =============================================================================
# CONFIG FILE — hello-world project
# =============================================================================
# Called at the top of every notebook with: %run ./config_file
#
# Detects environment (DEV/ACC/PRD) based on Workspace Org ID and sets
# catalog + schema variables for the medallion architecture.
# =============================================================================

# ── Environment detection ─────────────────────────────────────────
if spark.conf.get("spark.databricks.clusterUsageTags.clusterOwnerOrgId") == "7181820732839861":
    env = "d"    # DEV/TEST workspace
elif spark.conf.get("spark.databricks.clusterUsageTags.clusterOwnerOrgId") == "4796304964978539":
    env = "a"    # ACC workspace
elif spark.conf.get("spark.databricks.clusterUsageTags.clusterOwnerOrgId") == "4844910598668398":
    env = "p"    # PRD workspace

# ── Catalog & Medallion Layers ───────────────────────────────────
UNITY_CATALOG = f"automation_{env}"

BRONZE = f"{UNITY_CATALOG}.bronze"
SILVER = f"{UNITY_CATALOG}.silver"
GOLD   = f"{UNITY_CATALOG}.gold"

# ── Helper functions ─────────────────────────────────────────────
def bronze_table(name: str) -> str:
    """Get fully qualified bronze layer table name."""
    return f"{BRONZE}.{name}"

def silver_table(name: str) -> str:
    """Get fully qualified silver layer table name."""
    return f"{SILVER}.{name}"

def gold_table(name: str) -> str:
    """Get fully qualified gold layer table name."""
    return f"{GOLD}.{name}"

# ── Ensure schemas exist ─────────────────────────────────────────
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {BRONZE}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SILVER}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD}")

# ── Print config for debugging ───────────────────────────────────
print(f"Environment: {env}")
print(f"Catalog:     {UNITY_CATALOG}")
print(f"Bronze:      {BRONZE}")
print(f"Silver:      {SILVER}")
print(f"Gold:        {GOLD}")
