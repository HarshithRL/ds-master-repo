# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,04 - Promote DEV Dashboard
# MAGIC %md
# MAGIC # 04 - Promote DEV Dashboard
# MAGIC
# MAGIC **Purpose:** Detects changes between the DEV and Main dashboard, shows a diff report, identifies new metric view requirements, and promotes DEV → Main.
# MAGIC
# MAGIC **Workflow:**
# MAGIC 1. Edit `DEV - agent_dashboard_phase_1` in the UI
# MAGIC 2. Run this notebook to see what changed
# MAGIC 3. Review the diff report and metric view gaps
# MAGIC 4. Promote changes to the main `agent_dashboard_phase_1` dashboard
# MAGIC
# MAGIC **Run after:** Making UI changes in the DEV dashboard

# COMMAND ----------

# DBTITLE 1,Config
import json, os
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "automation_d", "Catalog")
dbutils.widgets.text("warehouse_id", "69ada62b2fb9b9e2", "Warehouse ID")
dbutils.widgets.dropdown("auto_promote", "no", ["no", "yes"], "Auto-promote (skip confirmation)")

CATALOG = dbutils.widgets.get("catalog")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")
AUTO_PROMOTE = dbutils.widgets.get("auto_promote") == "yes"
S = f"{CATALOG}.silver"

# Notebook is in src/ — go up once to get src/, up twice to get bundle root
PIPELINE_FOLDER = os.path.dirname(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
)
BUNDLE_ROOT = os.path.dirname(PIPELINE_FOLDER)
DASHBOARDS_FOLDER = f"{PIPELINE_FOLDER}/dashboards"
LVDASH_PATH = f"/Workspace{PIPELINE_FOLDER}/dashboards/agent_dashboard_phase_1.lvdash.json"

w = WorkspaceClient()

# ---------------------------------------------------------------------------
# Lakeview REST helpers — SDK-version-independent
# (ACC/PRD workspace SDK may lack w.lakeview.get/update/publish)
# ---------------------------------------------------------------------------
import requests as _req
from types import SimpleNamespace as _NS

_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
_lv_api = _ctx.apiUrl().get()
_lv_hdr = {"Authorization": f"Bearer {_ctx.apiToken().get()}", "Content-Type": "application/json"}

class _Lakeview:
    """REST wrapper for Lakeview API — works across all SDK versions."""
    def get(self, dashboard_id):
        r = _req.get(f"{_lv_api}/api/2.0/lakeview/dashboards/{dashboard_id}", headers=_lv_hdr)
        r.raise_for_status()
        d = r.json()
        sd = d.get("serialized_dashboard") or ""
        dn = d.get("display_name") or ""
        print(f"  [lv.get] id={dashboard_id}, display_name='{dn}', serialized_dashboard={len(sd)} chars (draft)")

        # Fall back to published version if draft is empty/too small
        if len(sd) < 100:
            print(f"  [lv.get] Draft content too small ({len(sd)} chars) — trying published version...")
            try:
                rp = _req.get(f"{_lv_api}/api/2.0/lakeview/dashboards/{dashboard_id}/published", headers=_lv_hdr)
                rp.raise_for_status()
                dp = rp.json()
                sd_pub = dp.get("serialized_dashboard") or ""
                if len(sd_pub) > len(sd):
                    sd = sd_pub
                    print(f"  [lv.get] Using published version: {len(sd)} chars")
                else:
                    print(f"  [lv.get] Published version also small ({len(sd_pub)} chars)")
            except Exception as e:
                print(f"  [lv.get] Could not fetch published version: {e}")

        if not sd or len(sd) < 100:
            print(f"  [lv.get] WARNING: serialized_dashboard is empty/too small!")
        return _NS(serialized_dashboard=sd, display_name=dn)

    def update(self, *, dashboard_id, serialized_dashboard, **kw):
        content_len = len(serialized_dashboard or "")
        if content_len < 100:
            raise RuntimeError(f"Refusing to update dashboard — content too small ({content_len} chars). Aborting to prevent data loss.")
        print(f"  [lv.update] id={dashboard_id}, sending {content_len} chars")
        r = _req.patch(f"{_lv_api}/api/2.0/lakeview/dashboards/{dashboard_id}",
                       headers=_lv_hdr, json={"serialized_dashboard": serialized_dashboard})
        r.raise_for_status()
        print(f"  [lv.update] status={r.status_code}")

    def publish(self, *, dashboard_id, warehouse_id, embed_credentials=True, **kw):
        print(f"  [lv.publish] id={dashboard_id}, warehouse={warehouse_id}")
        r = _req.post(f"{_lv_api}/api/2.0/lakeview/dashboards/{dashboard_id}/published",
                      headers=_lv_hdr, json={"warehouse_id": warehouse_id, "embed_credentials": embed_credentials})
        r.raise_for_status()
        print(f"  [lv.publish] status={r.status_code}")

lv = _Lakeview()

# ---------------------------------------------------------------------------
# Dynamic dashboard discovery — works across D / T / A / P targets
# Lists the dashboards folder via workspace API (resource_id = Lakeview ID)
# ---------------------------------------------------------------------------
MAIN_DASHBOARD_ID = None
DEV_DASHBOARD_ID = None

ws_dashboards = f"/Workspace{PIPELINE_FOLDER}/dashboards"
try:
    for obj in w.workspace.list(ws_dashboards):
        fname = (getattr(obj, 'path', '') or '').rsplit('/', 1)[-1].lower()
        rid = getattr(obj, 'resource_id', None)
        if not rid:
            continue
        if 'dev' in fname and 'agent_dashboard_phase_1' in fname:
            DEV_DASHBOARD_ID = rid
        elif 'agent_dashboard_phase_1' in fname:
            MAIN_DASHBOARD_ID = rid
except Exception as e:
    print(f"  Warning: could not list dashboards folder: {e}")

HAS_DEV = DEV_DASHBOARD_ID is not None

print(f"Catalog:        {CATALOG}")
print(f"Main dashboard: {MAIN_DASHBOARD_ID or 'NOT FOUND'}")
print(f"DEV dashboard:  {DEV_DASHBOARD_ID or 'NOT FOUND (diff/promote skipped)'}")
print(f"lvdash.json:    {LVDASH_PATH}")

if not MAIN_DASHBOARD_ID:
    raise RuntimeError("Main dashboard not found in dashboards folder. Run 'bundle deploy' first.")

# COMMAND ----------

# DBTITLE 1,Fetch Both Dashboards
# Fetch serialized JSON from both dashboards via Lakeview API

def fetch_dashboard(dashboard_id, label):
    """Fetch dashboard and return parsed serialized_dashboard dict."""
    draft = lv.get(dashboard_id)
    ser = json.loads(draft.serialized_dashboard)
    print(f"{label}: '{draft.display_name}' — {len(ser.get('datasets', []))} datasets, {len(ser.get('pages', []))} pages")
    return ser, draft.display_name

main_json, main_name = fetch_dashboard(MAIN_DASHBOARD_ID, "Main")

if HAS_DEV:
    dev_json, dev_name = fetch_dashboard(DEV_DASHBOARD_ID, "DEV")
    print(f"\nReady to compare: '{dev_name}' vs '{main_name}'")
else:
    dev_json, dev_name = None, None
    print("\nNo DEV dashboard — skipping diff. Will do _v2 sync + publish only.")

# COMMAND ----------

# DBTITLE 1,Diff Report — Datasets
# Compare datasets between DEV and Main dashboards
# Skipped in ACC/PRD where no DEV dashboard exists

new_datasets, removed_datasets, modified_datasets = [], [], []
dev_ds, main_ds = {}, {}

def _dataset_map(dashboard_json):
    """Return {dataset_name: dataset_dict} from serialized dashboard."""
    return {ds["name"]: ds for ds in dashboard_json.get("datasets", [])}

if not HAS_DEV:
    print("No DEV dashboard — dataset diff skipped.")
else:
    dev_ds = _dataset_map(dev_json)
    main_ds = _dataset_map(main_json)

    new_datasets = sorted(set(dev_ds) - set(main_ds))
    removed_datasets = sorted(set(main_ds) - set(dev_ds))
    common_datasets = sorted(set(dev_ds) & set(main_ds))

    for name in common_datasets:
        dev_config = json.dumps(dev_ds[name].get("config", {}), sort_keys=True)
        main_config = json.dumps(main_ds[name].get("config", {}), sort_keys=True)
        if dev_config != main_config:
            modified_datasets.append(name)

    print("=" * 70)
    print("DATASET DIFF REPORT")
    print("=" * 70)
    print(f"  DEV datasets:     {len(dev_ds)}")
    print(f"  Main datasets:    {len(main_ds)}")
    print(f"  New in DEV:       {len(new_datasets)}")
    print(f"  Removed from DEV: {len(removed_datasets)}")
    print(f"  Modified queries: {len(modified_datasets)}")
    print(f"  Unchanged:        {len(common_datasets) - len(modified_datasets)}")

    if new_datasets:
        print(f"\n  NEW datasets:")
        for ds in new_datasets:
            src = dev_ds[ds].get("config", {}).get("source", "")
            cat = dev_ds[ds].get("catalog", "")
            sch = dev_ds[ds].get("schema", "")
            print(f"    + {ds} [{cat}.{sch}]")
            if src:
                print(f"      Source: {src.strip()[:120]}..." if len(src.strip()) > 120 else f"      Source: {src.strip()}")

    if removed_datasets:
        print(f"\n  REMOVED datasets (in Main but not DEV):")
        for ds in removed_datasets:
            print(f"    - {ds}")

    if modified_datasets:
        print(f"\n  MODIFIED datasets:")
        for ds in modified_datasets:
            print(f"    ~ {ds}")
            dev_src = dev_ds[ds].get("config", {}).get("source", "").strip()
            main_src = main_ds[ds].get("config", {}).get("source", "").strip()
            print(f"      Main: {main_src[:100]}..." if len(main_src) > 100 else f"      Main: {main_src}")
            print(f"      DEV:  {dev_src[:100]}..." if len(dev_src) > 100 else f"      DEV:  {dev_src}")

    if not new_datasets and not removed_datasets and not modified_datasets:
        print("\n  No dataset changes detected.")

# COMMAND ----------

# DBTITLE 1,Diff Report — Pages & Widgets
# Compare pages and widgets between DEV and Main
# Skipped in ACC/PRD where no DEV dashboard exists

new_pages, removed_pages, modified_pages = [], [], []
total_changes = 0

def _page_map(dashboard_json):
    """Return {page_name: page_dict}."""
    return {p.get("displayName", f"page_{i}"): p for i, p in enumerate(dashboard_json.get("pages", []))}

def _count_widgets(page):
    return len(page.get("layout", []))

if not HAS_DEV:
    print("No DEV dashboard — page diff skipped.")
else:
    dev_pages = _page_map(dev_json)
    main_pages = _page_map(main_json)

    new_pages = sorted(set(dev_pages) - set(main_pages))
    removed_pages = sorted(set(main_pages) - set(dev_pages))
    common_pages = sorted(set(dev_pages) & set(main_pages))

    for pname in common_pages:
        dev_layout = json.dumps(dev_pages[pname].get("layout", []), sort_keys=True)
        main_layout = json.dumps(main_pages[pname].get("layout", []), sort_keys=True)
        if dev_layout != main_layout:
            modified_pages.append(pname)

    total_changes = len(new_datasets) + len(removed_datasets) + len(modified_datasets) + len(new_pages) + len(removed_pages) + len(modified_pages)

    print("=" * 70)
    print("PAGE & WIDGET DIFF REPORT")
    print("=" * 70)
    print(f"  DEV pages:     {len(dev_pages)}")
    print(f"  Main pages:    {len(main_pages)}")
    print(f"  New in DEV:    {len(new_pages)}")
    print(f"  Removed:       {len(removed_pages)}")
    print(f"  Modified:      {len(modified_pages)}")
    print(f"  Unchanged:     {len(common_pages) - len(modified_pages)}")

    if new_pages:
        print(f"\n  NEW pages:")
        for p in new_pages:
            print(f"    + {p} ({_count_widgets(dev_pages[p])} widgets)")
    if removed_pages:
        print(f"\n  REMOVED pages:")
        for p in removed_pages:
            print(f"    - {p}")
    if modified_pages:
        print(f"\n  MODIFIED pages:")
        for p in modified_pages:
            dev_wc = _count_widgets(dev_pages[p])
            main_wc = _count_widgets(main_pages[p])
            delta = dev_wc - main_wc
            sign = "+" if delta > 0 else ""
            print(f"    ~ {p}: {main_wc} -> {dev_wc} widgets ({sign}{delta})")

    print()
    if total_changes == 0:
        print("NO CHANGES DETECTED between DEV and Main.")
    else:
        print(f"TOTAL: {total_changes} change(s) detected. Review above and run Promote cell to apply.")

# COMMAND ----------

# DBTITLE 1,Detect Metric View Gaps
# Detect if DEV dashboard references metric views / tables not defined in notebook 03
# Skipped in ACC/PRD where no DEV dashboard exists
import re

unknown_silver = set()

KNOWN_METRIC_VIEWS = {
    "bot_usage_metrics", "copilot_analytics_metrics", "metric_agent_governance",
    "metric_credit_consumption", "metric_agent_feature_credit", "metric_environment_consumption"
}
KNOWN_METRIC_VIEWS_ALL = KNOWN_METRIC_VIEWS | {f"{mv}_v2" for mv in KNOWN_METRIC_VIEWS}
KNOWN_SILVER_TABLES = {
    "dim_agent", "fact_agent_credit", "bot_usage", "sl_purview_log",
    "silver_fact_interactions", "silver_dim_environment",
    "vw_agent_credit_detail", "vw_agent_governance",
    "vw_user_agent_usage", "vw_environment_daily"
}

def _extract_table_refs(datasets):
    """Extract catalog.schema.table references from dataset configs."""
    refs = set()
    for ds in datasets.values():
        catalog = ds.get("catalog", "")
        schema = ds.get("schema", "")
        source = ds.get("config", {}).get("source", "")
        if not isinstance(source, str) or not source.strip():
            continue
        fq = re.findall(r'\b(\w+\.\w+\.\w+)\b', source)
        refs.update(fq)
        if catalog and schema:
            unq = re.findall(r'(?:FROM|JOIN)\s+(\w+)(?=\s|$|,|\))', source, re.IGNORECASE)
            for t in unq:
                if t.upper() not in ('SELECT', 'WHERE', 'GROUP', 'ORDER', 'HAVING', 'LIMIT', 'UNION', 'LATERAL'):
                    refs.add(f"{catalog}.{schema}.{t}")
    return refs

if not HAS_DEV:
    print("No DEV dashboard \u2014 metric view gap analysis skipped.")
else:
    dev_refs = _extract_table_refs(dev_ds)
    main_refs = _extract_table_refs(main_ds)
    new_refs = dev_refs - main_refs
    silver_prefix = f"{CATALOG}.silver."
    new_silver_refs = {r for r in new_refs if r.startswith(silver_prefix)}
    new_other_refs = new_refs - new_silver_refs

    for ref in new_silver_refs:
        obj_name = ref.replace(silver_prefix, "")
        if obj_name not in KNOWN_METRIC_VIEWS_ALL and obj_name not in KNOWN_SILVER_TABLES:
            unknown_silver.add(obj_name)

    print("=" * 70)
    print("METRIC VIEW GAP ANALYSIS")
    print("=" * 70)
    print(f"  DEV table/view references:  {len(dev_refs)}")
    print(f"  Main table/view references: {len(main_refs)}")
    print(f"  New references in DEV:      {len(new_refs)}")

    if new_silver_refs:
        print(f"\n  New silver references:")
        for r in sorted(new_silver_refs):
            obj_name = r.replace(silver_prefix, "")
            status = "KNOWN" if obj_name in KNOWN_METRIC_VIEWS_ALL or obj_name in KNOWN_SILVER_TABLES else "UNKNOWN - needs definition"
            print(f"    {r} [{status}]")
    if new_other_refs:
        print(f"\n  New non-silver references:")
        for r in sorted(new_other_refs):
            print(f"    {r}")

    if unknown_silver:
        print(f"\n  \u26a0\ufe0f  ACTION REQUIRED: {len(unknown_silver)} new silver object(s) need definitions:")
        for obj in sorted(unknown_silver):
            print(f"    - {silver_prefix}{obj}")
        print("  \u2192 Add metric view or table definitions to notebook 03_metrics_validate_publish")
    else:
        print(f"\n  \u2705 All DEV references are covered by existing metric views and tables.")
        all_dev_silver = {r for r in dev_refs if r.startswith(silver_prefix)}
        print(f"\n  All silver objects used by DEV ({len(all_dev_silver)}):")
        for r in sorted(all_dev_silver):
            print(f"    {r}")

# COMMAND ----------

# DBTITLE 1,Sync _v2 Metric View Names in Dashboard
# ---------------------------------------------------------------------------
# Detect which metric views use _v2 suffix (permission fallback from nb 03)
# and sync references in the Main dashboard JSON.
# This replaces the _v2 sync logic that was previously in notebook 03.
# ---------------------------------------------------------------------------

ALL_METRIC_VIEWS = ["bot_usage_metrics", "copilot_analytics_metrics", "metric_agent_governance",
                    "metric_credit_consumption", "metric_agent_feature_credit", "metric_environment_consumption"]

# Query information_schema to find which names actually exist
existing_views = set()
try:
    rows = spark.sql(f"""
        SELECT table_name
        FROM {CATALOG}.information_schema.tables
        WHERE table_schema = 'silver'
          AND table_name IN ({', '.join(f"'{mv}'" for mv in ALL_METRIC_VIEWS)},
                              {', '.join(f"'{mv}_v2'" for mv in ALL_METRIC_VIEWS)})
    """).collect()
    existing_views = {r.table_name for r in rows}
except Exception as e:
    print(f"  Warning: could not query information_schema: {e}")
    print("  Skipping _v2 sync — dashboard will keep current references.")

# Determine the correct name for each metric view
metric_view_names = {}  # {base_name: actual_name_in_catalog}
for mv in ALL_METRIC_VIEWS:
    if f"{mv}_v2" in existing_views:
        metric_view_names[mv] = f"{mv}_v2"
    elif mv in existing_views:
        metric_view_names[mv] = mv
    else:
        metric_view_names[mv] = None  # doesn't exist at all

print("Metric view name resolution:")
for base, actual in metric_view_names.items():
    if actual is None:
        print(f"  ⚠️  {base} — NOT FOUND in catalog")
    elif actual != base:
        print(f"  {base} → {actual} (renamed)")
    else:
        print(f"  {base} (original)")

# ---------------------------------------------------------------------------
# Apply _v2 sync to the Main dashboard JSON
# We work on main_json (the parsed dict) by manipulating the serialized string
# ---------------------------------------------------------------------------
import copy

# Re-fetch Main dashboard as string for manipulation
main_draft = lv.get(MAIN_DASHBOARD_ID)
main_ser_str = main_draft.serialized_dashboard

# Patch catalog references to match the current environment.
# The lvdash.json source file is seeded from DEV and has automation_d hardcoded
# in every dataset's "catalog" field and SQL source strings.
if CATALOG != "automation_d" and "automation_d" in main_ser_str:
    main_ser_str = main_ser_str.replace('"automation_d"', f'"{CATALOG}"')
    main_ser_str = main_ser_str.replace("automation_d.silver", f"{CATALOG}.silver")
    print(f"  Catalog patched: automation_d \u2192 {CATALOG}")

v2_changes = 0
for mv, actual in metric_view_names.items():
    if actual is None:
        continue
    orig_ref = f"{S}.{mv}"
    v2_ref = f"{S}.{mv}_v2"
    target_ref = f"{S}.{actual}"

    if actual.endswith("_v2"):
        # Should point to _v2
        if orig_ref in main_ser_str and v2_ref not in main_ser_str:
            main_ser_str = main_ser_str.replace(orig_ref, v2_ref)
            print(f"  Synced: {orig_ref} → {v2_ref}")
            v2_changes += 1
    else:
        # Should point to original — revert any _v2
        if v2_ref in main_ser_str:
            main_ser_str = main_ser_str.replace(v2_ref, orig_ref)
            print(f"  Reverted: {v2_ref} → {orig_ref}")
            v2_changes += 1

if v2_changes > 0:
    print(f"\n  {v2_changes} metric view reference(s) synced in Main dashboard.")
else:
    print("\n  All metric view references already correct.")

# COMMAND ----------

# DBTITLE 1,Promote DEV → Main + Publish
# ---------------------------------------------------------------------------
# Promote DEV → Main (if changes) + sync _v2 names + always publish
# This is the single owner of dashboard operations (moved from notebook 03)
# ---------------------------------------------------------------------------

# Determine what to write to the Main dashboard
has_dev_changes = HAS_DEV and total_changes > 0
final_ser_str = main_ser_str  # start with _v2-synced Main JSON

# --- Gate: if DEV has changes, decide whether to promote ---
if has_dev_changes and not AUTO_PROMOTE:
    print(f"\u2139\ufe0f  {total_changes} DEV change(s) detected but auto_promote=no.")
    print(f"   Set widget 'auto_promote' = 'yes' and re-run to include DEV changes.")
    print("\nDEV changes summary:")
    if new_datasets: print(f"  + {len(new_datasets)} new dataset(s)")
    if removed_datasets: print(f"  - {len(removed_datasets)} removed dataset(s)")
    if modified_datasets: print(f"  ~ {len(modified_datasets)} modified dataset(s)")
    if new_pages: print(f"  + {len(new_pages)} new page(s)")
    if removed_pages: print(f"  - {len(removed_pages)} removed page(s)")
    if modified_pages: print(f"  ~ {len(modified_pages)} modified page(s)")
    if unknown_silver:
        print(f"\n  \u26a0\ufe0f  WARNING: {len(unknown_silver)} unknown silver references \u2014 add definitions first!")
    print(f"\nProceeding with _v2 sync + publish only (no DEV promotion).")

elif has_dev_changes and AUTO_PROMOTE:
    # Promote: use DEV JSON as the base, then apply _v2 sync on top
    print(f"Promoting {total_changes} DEV change(s) to Main...")
    dev_draft = lv.get(DEV_DASHBOARD_ID)
    final_ser_str = dev_draft.serialized_dashboard

    # Patch catalog references from DEV to current environment
    if CATALOG != "automation_d" and "automation_d" in final_ser_str:
        final_ser_str = final_ser_str.replace('"automation_d"', f'"{CATALOG}"')
        final_ser_str = final_ser_str.replace("automation_d.silver", f"{CATALOG}.silver")
        print(f"  Catalog patched: automation_d \u2192 {CATALOG}")

    # Apply _v2 metric view sync to the promoted DEV JSON
    for mv, actual in metric_view_names.items():
        if actual is None:
            continue
        orig_ref = f"{S}.{mv}"
        v2_ref = f"{S}.{mv}_v2"
        if actual.endswith("_v2"):
            if orig_ref in final_ser_str and v2_ref not in final_ser_str:
                final_ser_str = final_ser_str.replace(orig_ref, v2_ref)
        else:
            if v2_ref in final_ser_str:
                final_ser_str = final_ser_str.replace(v2_ref, orig_ref)
    print(f"  \u2713 DEV changes merged with _v2 sync")

else:
    print("No DEV changes detected. Proceeding with _v2 sync + publish.")

# --- Fallback: if Main dashboard content is empty (e.g. initial DAB deploy in PROD where no DEV dashboard exists), seed from lvdash.json ---
if len(final_ser_str or "") < 100:
    print(f"\n⚠️ Main dashboard content is empty ({len(final_ser_str or '')} chars). Attempting fallback seed from candidate files...")
    seed_loaded = False
    candidate_paths = [
        LVDASH_PATH,
        f"/Workspace{PIPELINE_FOLDER}/dashboards/DEV -  agent_dashboard_phase_1.lvdash.json",
        f"/Workspace{PIPELINE_FOLDER}/dashboards/agent_dashboard_phase_1.lvdash.json",
        f"/Volumes/{CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data/_dashboard_template.json",
        "/Volumes/automation_d/bronze/bronze_volume/Copilot_Dashboard_Data/_dashboard_template.json"
    ]
    for candidate_path in candidate_paths:
        try:
            if os.path.exists(candidate_path):
                with open(candidate_path, "r", encoding="utf-8") as f:
                    dash_file_data = json.load(f)
                    candidate_ser = ""
                    if isinstance(dash_file_data, dict) and "serialized_dashboard" in dash_file_data:
                        ser_val = dash_file_data["serialized_dashboard"]
                        candidate_ser = json.dumps(ser_val) if isinstance(ser_val, dict) else str(ser_val)
                    else:
                        candidate_ser = json.dumps(dash_file_data)
                    
                    if len(candidate_ser) >= 100:
                        final_ser_str = candidate_ser
                        print(f"  ✓ Loaded valid seed content from {candidate_path} ({len(final_ser_str)} chars)")
                        seed_loaded = True
                        break
                    else:
                        print(f"  ⚠️ Candidate file {candidate_path} content too small ({len(candidate_ser)} chars) — trying next...")
        except Exception as e:
            print(f"  ⚠️ Could not read {candidate_path}: {e}")

    if seed_loaded:
        # Patch catalog references for the loaded seed
        if CATALOG != "automation_d" and "automation_d" in final_ser_str:
            final_ser_str = final_ser_str.replace('"automation_d"', f'"{CATALOG}"')
            final_ser_str = final_ser_str.replace("automation_d.silver", f"{CATALOG}.silver")
            print(f"  Catalog patched: automation_d → {CATALOG}")

        # Apply _v2 metric view sync to the seeded JSON
        for mv, actual in metric_view_names.items():
            if actual is None:
                continue
            orig_ref = f"{S}.{mv}"
            v2_ref = f"{S}.{mv}_v2"
            if actual.endswith("_v2"):
                if orig_ref in final_ser_str and v2_ref not in final_ser_str:
                    final_ser_str = final_ser_str.replace(orig_ref, v2_ref)
            else:
                if v2_ref in final_ser_str:
                    final_ser_str = final_ser_str.replace(v2_ref, orig_ref)
    else:
        print("\n⚠️ Main dashboard content is empty and no seed file could be loaded — skipping update and publish.")
        if has_dev_changes:
            print("   Set auto_promote='yes' and re-run to populate Main from DEV.")
        dbutils.notebook.exit(json.dumps({
            "status": "SKIPPED",
            "reason": "Main dashboard empty, no seed file found",
            "dashboard_id": MAIN_DASHBOARD_ID,
            "dev_changes": total_changes if HAS_DEV else 0,
            "v2_synced": v2_changes
        }))

# --- Update Main dashboard ---
lv.update(
    dashboard_id=MAIN_DASHBOARD_ID,
    serialized_dashboard=final_ser_str
)
print(f"  \u2713 Main dashboard updated")

# --- Publish ---
lv.publish(
    dashboard_id=MAIN_DASHBOARD_ID,
    warehouse_id=WAREHOUSE_ID,
    embed_credentials=True
)
print(f"  \u2713 Main dashboard published")

# --- Update lvdash.json for Git tracking ---
try:
    lvdash_content = {
        "display_name": main_name,
        "warehouse_id": WAREHOUSE_ID,
        "serialized_dashboard": final_ser_str
    }
    with open(LVDASH_PATH, "w") as f:
        json.dump(lvdash_content, f, indent=2)
    print(f"  \u2713 lvdash.json updated: {LVDASH_PATH}")
    print(f"    \u2192 Commit this change to Git to track the dashboard update")
except Exception as e:
    print(f"  \u26a0\ufe0f  Could not update lvdash.json: {e}")

# --- Update volume template ---
try:
    VOLUME_BASE = f"/Volumes/{CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data"
    TEMPLATE_FILE = f"{VOLUME_BASE}/_dashboard_template.json"
    tmpl = {"display_name": main_name, "serialized_dashboard": final_ser_str}
    with open(TEMPLATE_FILE, "w") as f:
        json.dump(tmpl, f, indent=2)
    print(f"  \u2713 Volume template updated")
except Exception as e:
    print(f"  \u26a0\ufe0f  Could not update volume template: {e}")

# --- Summary ---
status = "PROMOTED" if (has_dev_changes and AUTO_PROMOTE) else "PUBLISHED"
print(f"\n\u2705 Done. Status: {status}")
if has_dev_changes and AUTO_PROMOTE:
    print(f"   {total_changes} DEV change(s) promoted + _v2 synced + published.")
elif v2_changes > 0:
    print(f"   {v2_changes} _v2 reference(s) synced + published (no DEV promotion).")
else:
    print(f"   Published (no changes needed).")

dbutils.notebook.exit(json.dumps({
    "status": status,
    "dashboard_id": MAIN_DASHBOARD_ID,
    "dev_changes": total_changes,
    "v2_synced": v2_changes
}))
