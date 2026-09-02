# Databricks notebook source

# COMMAND ----------

# =============================================================================
# CONFIG FILE — agent-dashboard project
# =============================================================================
# Called at the top of every notebook with: %run ./config_file
#
# Detects environment (DEV/ACC/PRD) from Workspace Org ID and sets
# catalog + schema + volume helpers for the medallion architecture.
# =============================================================================

# ── Environment detection ─────────────────────────────────────────
# Serverless jobs often lack clusterOwnerOrgId; fall back to workspaceUrl.
def _detect_org_id() -> str:
    for key in (
        "spark.databricks.clusterUsageTags.clusterOwnerOrgId",
        "spark.databricks.workspaceId",
    ):
        try:
            val = spark.conf.get(key)
            if val:
                return str(val)
        except Exception:
            pass
    try:
        url = spark.conf.get("spark.databricks.workspaceUrl")
        # e.g. adb-7181820732839861.1.azuredatabricks.net
        if url and url.startswith("adb-"):
            return url.split(".")[0].replace("adb-", "")
    except Exception:
        pass
    return ""


_org_id = _detect_org_id()
if _org_id == "7181820732839861":
    env = "d"  # DEV/TEST workspace
elif _org_id == "4796304964978539":
    env = "a"  # ACC workspace
elif _org_id == "4844910598668398":
    env = "p"  # PRD workspace
else:
    # Missing tag — default to DEV catalog (safe for local D target)
    env = "d"
    print(f"WARNING: could not detect workspace org id (got {_org_id!r}); defaulting env=d")

# ── Catalog & Medallion Layers ───────────────────────────────────
UNITY_CATALOG = f"automation_{env}"

BRONZE = f"{UNITY_CATALOG}.bronze"
SILVER = f"{UNITY_CATALOG}.silver"
GOLD = f"{UNITY_CATALOG}.gold"

# Volume used by file-arrival trigger + notebook 01 ingest
BRONZE_VOLUME = f"/Volumes/{UNITY_CATALOG}/bronze/bronze_volume/"

# DEV defaults; job base_parameters / widgets may override in publish notebook
DEFAULT_DASHBOARD_ID = "01f19237ae0419ea830abdda6219869d"
DEFAULT_WAREHOUSE_ID = "69ada62b2fb9b9e2"


def bronze_table(name: str) -> str:
    """Fully qualified bronze table name."""
    return f"{BRONZE}.{name}"


def silver_table(name: str) -> str:
    """Fully qualified silver table name."""
    return f"{SILVER}.{name}"


def gold_table(name: str) -> str:
    """Fully qualified gold table name."""
    return f"{GOLD}.{name}"


def fq(schema_table: str) -> str:
    """
    Rewrite legacy three-part names that hardcode automation_d.* into the
    current catalog. Accepts 'automation_d.silver.foo', 'silver.foo', or 'foo'.
    """
    parts = schema_table.split(".")
    if len(parts) == 3:
        return f"{UNITY_CATALOG}.{parts[1]}.{parts[2]}"
    if len(parts) == 2:
        return f"{UNITY_CATALOG}.{parts[0]}.{parts[1]}"
    return f"{SILVER}.{parts[0]}"


def rewrite_sql(sql: str) -> str:
    """Replace hardcoded automation_d catalog refs with the active catalog."""
    return (
        sql.replace("automation_d.silver", SILVER)
        .replace("automation_d.bronze", BRONZE)
        .replace("automation_d.gold", GOLD)
        .replace("/Volumes/automation_d/bronze/bronze_volume/", BRONZE_VOLUME)
        .replace("/Volumes/automation_d/bronze/bronze_volume", BRONZE_VOLUME.rstrip("/"))
    )


# ── Ensure schemas exist ─────────────────────────────────────────
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {BRONZE}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SILVER}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD}")

# ── Print config for debugging ───────────────────────────────────
print(f"Environment:    {env}")
print(f"Catalog:        {UNITY_CATALOG}")
print(f"Bronze:         {BRONZE}")
print(f"Silver:         {SILVER}")
print(f"Gold:           {GOLD}")
print(f"Bronze volume:  {BRONZE_VOLUME}")
