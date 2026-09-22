# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,00 - SharePoint to Volume
# MAGIC %md
# MAGIC # 00 - SharePoint to Volume
# MAGIC
# MAGIC **Purpose:** Downloads files from the Copilot Dashboard SharePoint folder into a timestamped subfolder in the UC volume.
# MAGIC
# MAGIC **Validation rules:**
# MAGIC - Downloads all 7 required files from SharePoint
# MAGIC - If a file is **missing from SharePoint**, searches previous runs / archive for a fallback copy
# MAGIC - **WARN** when using a fallback (stale data) — pipeline continues
# MAGIC - **FAIL** only if a file is missing from SharePoint AND no previous copy exists anywhere
# MAGIC - **WARN** if a file hasn't been modified in >7 days (stale but acceptable)
# MAGIC
# MAGIC **Target volume:** `/Volumes/automation_d/bronze/bronze_volume/Copilot_Dashboard_Data/<YYYY-MM-DD_HH-MM-SS>/`
# MAGIC
# MAGIC **Next step:** Run `01_bronze_ingestion`

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# MAGIC %pip install msal requests --quiet

# COMMAND ----------

# DBTITLE 1,Configuration
import os
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Parameters (from run_pipeline or manual)
# ---------------------------------------------------------------------------
dbutils.widgets.text("catalog", "automation_d", "Catalog")
INFRA_CATALOG = dbutils.widgets.get("catalog")

# Derive secret scope from catalog suffix
_SCOPE_MAP = {"automation_d": "WE-SPOKE-MDP-AUT-T-KV", "automation_a": "WE-SPOKE-MDP-AUT-A-KV", "automation_p": "WE-SPOKE-MDP-AUT-P-KV"}
SECRET_SCOPE = _SCOPE_MAP.get(INFRA_CATALOG, "WE-SPOKE-MDP-AUT-T-KV")
print(f"Catalog: {INFRA_CATALOG}, Secret scope: {SECRET_SCOPE}")

# ---------------------------------------------------------------------------
# Credentials (Azure AD SPN with Sites.Read.All)
# ---------------------------------------------------------------------------
TENANT_ID = "e23c7299-f64d-4de4-a6a1-b40d3145528c"
KV_SECRET_CLIENT_ID = "SHAREPOINT-CLIENT-ID"
KV_SECRET_CLIENT_SECRET = "SHAREPOINT-CLIENT-SECRET"

# ---------------------------------------------------------------------------
# SharePoint target
# ---------------------------------------------------------------------------
SHAREPOINT_HOST = "etexgroup.sharepoint.com"
SHAREPOINT_SITE_PATH = "/teams/etex-rpa"
SHAREPOINT_FOLDER_PATH = "Data Science/PROJECTS/Copilot Dashboard/2 Stakeholder Inputs/Data/UAT"

# ---------------------------------------------------------------------------
# Volume target
# ---------------------------------------------------------------------------
VOLUME_BASE = f"/Volumes/{INFRA_CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data"
os.makedirs(VOLUME_BASE, exist_ok=True)

# ---------------------------------------------------------------------------
# EXPECTED FILES - the dashboard requires exactly these 7 canonical tables.
# Each entry: canonical_base_name -> set of acceptable SharePoint display names.
# At least one file matching each canonical name must be present.
# ---------------------------------------------------------------------------
EXPECTED_CANONICAL = {
    "agents_inventory",
    "agent_level_credit_consumption",
    "environment_level_credit_consumption",
    "user_level_credit_consumption",
    "copilot_studio_kit_all_records",
    "bot_usage_pp_coe_kit",
    "microsoft_purview_audit_log",
}

# Staleness threshold (days) for warn
STALENESS_DAYS = 7

print(f"Volume base: {VOLUME_BASE}")
print(f"Expected files: {len(EXPECTED_CANONICAL)}")

# COMMAND ----------

# DBTITLE 1,SharePoint Rename Map
import re

# ---------------------------------------------------------------------------
# SharePoint display name -> canonical file name
# ---------------------------------------------------------------------------
SHAREPOINT_RENAME_MAP = {
    "agents inventory.xlsx":                               "agents_inventory.xlsx",
    "agents inventory.csv":                                "agents_inventory.csv",
    "agent-level credit consumption.xlsx":                 "agent_level_credit_consumption.xlsx",
    "agent-level credit consumption.csv":                  "agent_level_credit_consumption.csv",
    "agent-level credit consumption - last 30 days.csv":   "agent_level_credit_consumption.csv",
    "agent-level credit consumption - last 30 days.xlsx":  "agent_level_credit_consumption.xlsx",
    "environment-level credit consumption.xlsx":           "environment_level_credit_consumption.xlsx",
    "environment-level credit consumption.csv":            "environment_level_credit_consumption.csv",
    "environment-level credit consumption - last 30 days.csv":  "environment_level_credit_consumption.csv",
    "environment-level credit consumption - last 30 days.xlsx": "environment_level_credit_consumption.xlsx",
    "user-level credit consumption.xlsx":                  "user_level_credit_consumption.xlsx",
    "user-level credit consumption.csv":                   "user_level_credit_consumption.csv",
    "user-level credit consumption - last 30 days.csv":    "user_level_credit_consumption.csv",
    "user-level credit consumption - last 30 days.xlsx":   "user_level_credit_consumption.xlsx",
    "microsoft purview audit log.xlsx":                    "microsoft_purview_audit_log.xlsx",
    "microsoft purview audit log.csv":                     "microsoft_purview_audit_log.csv",
    "microsoft purview audit log - last 180 days.csv":     "microsoft_purview_audit_log.csv",
    "microsoft purview audit log - last 180 days.xlsx":    "microsoft_purview_audit_log.xlsx",
    "bot usage - pp coe kit.xlsx":                         "bot_usage_pp_coe_kit.xlsx",
    "bot usage - pp coe kit (1).xlsx":                     "bot_usage_pp_coe_kit.xlsx",
    "pva bot usages.xlsx":                                 "bot_usage_pp_coe_kit.xlsx",
    "pva bot usages.csv":                                  "bot_usage_pp_coe_kit.csv",
    "copilot studio kit all records.xlsx":                 "copilot_studio_kit_all_records.xlsx",
    "copilot_studio_kit_all_records.xlsx":                 "copilot_studio_kit_all_records.xlsx",
}

KEYWORD_RULES = [
    (["agent", "level", "credit"],       "agent_level_credit_consumption"),
    (["environment", "level", "credit"], "environment_level_credit_consumption"),
    (["user", "level", "credit"],        "user_level_credit_consumption"),
    (["agents", "inventory"],            "agents_inventory"),
    (["purview", "audit"],               "microsoft_purview_audit_log"),
    (["pva", "bot"],                     "bot_usage_pp_coe_kit"),
    (["bot", "usage"],                   "bot_usage_pp_coe_kit"),
    (["copilot", "studio", "kit"],       "copilot_studio_kit_all_records"),
]


def get_canonical_name(display_name: str) -> str:
    """Resolve SharePoint display name to canonical volume file name."""
    lower = display_name.lower()
    if lower in SHAREPOINT_RENAME_MAP:
        return SHAREPOINT_RENAME_MAP[lower]
    for keywords, base in KEYWORD_RULES:
        if all(kw in lower for kw in keywords):
            ext = os.path.splitext(display_name)[1].lower() or ".xlsx"
            return f"{base}{ext}"
    # Fallback: sanitize
    name = re.sub(r'\.(xlsx|xls|csv)\Z', '', display_name, flags=re.IGNORECASE)
    name = re.sub(r'[^a-zA-Z0-9]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_').lower()
    ext = os.path.splitext(display_name)[1].lower() or ".xlsx"
    return f"{name}{ext}"


def canonical_base(filename: str) -> str:
    """Strip extension from canonical filename to get the base name."""
    return re.sub(r'\.(xlsx|xls|csv)\Z', '', filename, flags=re.IGNORECASE)


print("Rename map loaded.")

# COMMAND ----------

# DBTITLE 1,Authenticate to Microsoft Graph
import msal
import requests
import json

CLIENT_ID = dbutils.secrets.get(scope=SECRET_SCOPE, key=KV_SECRET_CLIENT_ID)
CLIENT_SECRET = dbutils.secrets.get(scope=SECRET_SCOPE, key=KV_SECRET_CLIENT_SECRET)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPE = ["https://graph.microsoft.com/.default"]

app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    client_credential=CLIENT_SECRET,
)
token_result = app.acquire_token_for_client(scopes=SCOPE)
assert "access_token" in token_result, f"Auth failed: {token_result.get('error_description')}"

HEADERS = {"Authorization": f"Bearer {token_result['access_token']}"}
print("Successfully authenticated to Microsoft Graph API.")

# COMMAND ----------

# DBTITLE 1,Resolve SharePoint Site & Drive
site_url = f"{GRAPH_BASE}/sites/{SHAREPOINT_HOST}:{SHAREPOINT_SITE_PATH}"
site_resp = requests.get(site_url, headers=HEADERS)
site_resp.raise_for_status()
site_data = site_resp.json()
SITE_ID = site_data["id"]
print(f"Site: {site_data['displayName']}  (ID: {SITE_ID})")

drives_resp = requests.get(f"{GRAPH_BASE}/sites/{SITE_ID}/drives", headers=HEADERS)
drives_resp.raise_for_status()
DRIVE_ID = next(d["id"] for d in drives_resp.json()["value"] if d["driveType"] == "documentLibrary")
print(f"Drive ID: {DRIVE_ID}")

# COMMAND ----------

# DBTITLE 1,List SharePoint Files
from urllib.parse import quote

def list_sharepoint_files(drive_id, folder_path):
    """Return list of file metadata dicts from the specified SharePoint folder."""
    encoded = quote(folder_path, safe='')
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{encoded}:/children"
    files = []
    while url:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("value", []):
            if "file" in item:  # skip folders
                files.append({
                    "id": item["id"],
                    "name": item["name"],
                    "size": item["size"],
                    "lastModifiedDateTime": item["lastModifiedDateTime"],
                    "downloadUrl": item.get("@microsoft.graph.downloadUrl"),
                })
        url = data.get("@odata.nextLink")
    return files

# List only Excel and CSV files
all_sp_files = list_sharepoint_files(DRIVE_ID, SHAREPOINT_FOLDER_PATH)
sp_files = [f for f in all_sp_files if f["name"].lower().endswith((".xlsx", ".xls", ".csv"))]

print(f"Found {len(sp_files)} Excel/CSV file(s) in SharePoint folder:")
for f in sp_files:
    print(f"  {f['name']:60s} {f['size']/1024:.1f} KB  modified {f['lastModifiedDateTime']}")

# COMMAND ----------

# DBTITLE 1,Resolve: what to download, what to reuse
# ---------------------------------------------------------------------------
# INCREMENTAL SYNC: only download files that changed on SharePoint.
# For unchanged files, reuse from the most recent subfolder.
# For files missing from SP, walk backwards through all subfolders.
# Only FAIL if a file exists nowhere at all.
# ---------------------------------------------------------------------------
import json as _json

SYNC_STATE_FILE = os.path.join(VOLUME_BASE, ".sync_state.json")

# --- Step 1: Map SharePoint files to canonical bases ---
sp_resolved = {}  # canonical_base -> {"sp_file", "canonical_name", "modified"}
for f in sp_files:
    canon = get_canonical_name(f["name"])
    base = canonical_base(canon)
    mod_dt = datetime.fromisoformat(f["lastModifiedDateTime"].replace("Z", "+00:00"))
    if base not in sp_resolved or mod_dt > sp_resolved[base]["modified"]:
        sp_resolved[base] = {
            "sp_file": f,
            "canonical_name": canon,
            "modified": mod_dt,
        }

# --- Step 2: Load previous sync state ---
prev_state = {}  # canonical_base -> {"modified_iso": ..., "subfolder": ...}
try:
    with open(SYNC_STATE_FILE, "r") as fh:
        prev_state = _json.load(fh)
    print(f"Previous sync state loaded ({len(prev_state)} files tracked)")
except (FileNotFoundError, _json.JSONDecodeError):
    print("No previous sync state found - will download everything.")

# --- Step 3: Build list of previous subfolders (most recent first) ---
prev_subfolders = []
try:
    entries = dbutils.fs.ls(VOLUME_BASE)
    prev_subfolders = sorted(
        [e.path.replace("dbfs:", "") for e in entries if e.isDir()],
        reverse=True,
    )
except Exception:
    pass

# Also include archive / new_set / root as last-resort fallbacks
fallback_extras = []
archive_base = f"/Volumes/{INFRA_CATALOG}/bronze/bronze_volume/archive"
try:
    for sub in sorted(dbutils.fs.ls(archive_base), key=lambda e: e.name, reverse=True):
        if sub.isDir():
            fallback_extras.append(sub.path.replace("dbfs:", ""))
except Exception:
    pass
fallback_extras.append(f"/Volumes/{INFRA_CATALOG}/bronze/bronze_volume/new_set")
fallback_extras.append(f"/Volumes/{INFRA_CATALOG}/bronze/bronze_volume")

def find_in_subfolders(target_base, search_dirs):
    """Walk through directories to find a file matching target_base. Returns (path, name, source_dir) or None."""
    for loc in search_dirs:
        try:
            for f in dbutils.fs.ls(loc):
                if f.isDir():
                    continue
                fbase = canonical_base(get_canonical_name(f.name))
                if fbase == target_base:
                    return f.path.replace("dbfs:", ""), f.name, loc
        except Exception:
            continue
    return None

# --- Step 4: Classify each expected file ---
# Actions: DOWNLOAD (changed on SP), REUSE (unchanged, copy from prev), FALLBACK (not on SP)
actions = {}   # canonical_base -> {"action": ..., "detail": ...}
warnings = []
now_utc = datetime.now(timezone.utc)

print("=" * 70)
print("INCREMENTAL SYNC PLAN")
print("=" * 70)

for base in sorted(EXPECTED_CANONICAL):
    if base in sp_resolved:
        info = sp_resolved[base]
        sp_mod_iso = info["modified"].isoformat()
        prev_mod_iso = prev_state.get(base, {}).get("modified_iso", "")

        age = now_utc - info["modified"]
        if age > timedelta(days=STALENESS_DAYS):
            warnings.append(f"STALE: {base} is {age.days} days old on SharePoint")

        if sp_mod_iso == prev_mod_iso:
            # Unchanged — find in previous subfolders
            found = find_in_subfolders(base, prev_subfolders)
            if found:
                path, name, src = found
                actions[base] = {
                    "action": "REUSE",
                    "source_path": path,
                    "source_name": name,
                    "source_dir": src,
                    "canonical_name": info["canonical_name"],
                    "modified": info["modified"],
                }
                src_short = src.rstrip("/").split("/")[-1]
                print(f"  \u26aa {base:45s} REUSE     (unchanged, from {src_short})")
            else:
                # Has sync state but file missing from disk — re-download
                actions[base] = {
                    "action": "DOWNLOAD",
                    "sp_file": info["sp_file"],
                    "canonical_name": info["canonical_name"],
                    "modified": info["modified"],
                    "reason": "file missing from previous subfolders",
                }
                print(f"  \U0001f7e2 {base:45s} DOWNLOAD  (file missing from disk)")
        else:
            # Changed — download fresh
            actions[base] = {
                "action": "DOWNLOAD",
                "sp_file": info["sp_file"],
                "canonical_name": info["canonical_name"],
                "modified": info["modified"],
                "reason": "modified on SharePoint" if prev_mod_iso else "first sync",
            }
            reason = "modified" if prev_mod_iso else "first sync"
            print(f"  \U0001f7e2 {base:45s} DOWNLOAD  ({reason})")
    else:
        # Not on SharePoint — walk backwards through all subfolders
        found = find_in_subfolders(base, prev_subfolders + fallback_extras)
        if found:
            path, name, src = found
            actions[base] = {
                "action": "FALLBACK",
                "source_path": path,
                "source_name": name,
                "source_dir": src,
                "canonical_name": f"{base}{os.path.splitext(name)[1]}",
            }
            src_short = src.rstrip("/").split("/")[-1]
            w = f"NOT ON SP: {base} — using fallback from {src_short}/{name}"
            warnings.append(w)
            print(f"  \U0001f7e0 {base:45s} FALLBACK  ({src_short}/{name})")
        else:
            actions[base] = {"action": "MISSING"}
            print(f"  \u274c {base:45s} MISSING   (nowhere!)")

# --- Step 5: Check for truly missing ---
truly_missing = [b for b, a in actions.items() if a["action"] == "MISSING"]
if truly_missing:
    msg = (
        f"FATAL: {len(truly_missing)} file(s) not found anywhere:\n"
        + "\n".join(f"  - {m}" for m in sorted(truly_missing))
    )
    print(f"\n{msg}")
    raise FileNotFoundError(msg)

# Summary
n_dl = sum(1 for a in actions.values() if a["action"] == "DOWNLOAD")
n_re = sum(1 for a in actions.values() if a["action"] == "REUSE")
n_fb = sum(1 for a in actions.values() if a["action"] == "FALLBACK")
print(f"\nPlan: {n_dl} download + {n_re} reuse + {n_fb} fallback = {len(actions)} files")
if warnings:
    print(f"\n\u26a0 {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  - {w}")
print("=" * 70)

# COMMAND ----------

# DBTITLE 1,Execute: download, reuse, or fallback
import shutil

def download_file(file_meta, target_dir):
    """Download a single file from SharePoint and return (path, bytes)."""
    name = file_meta["name"]
    download_url = file_meta.get("downloadUrl")
    if not download_url:
        content_url = f"{GRAPH_BASE}/drives/{DRIVE_ID}/items/{file_meta['id']}/content"
        resp = requests.get(content_url, headers=HEADERS, allow_redirects=False)
        if resp.status_code in (301, 302):
            download_url = resp.headers["Location"]
        else:
            target_path = os.path.join(target_dir, name)
            with open(target_path, "wb") as out:
                out.write(resp.content)
            return target_path, len(resp.content)
    resp = requests.get(download_url, stream=True)
    resp.raise_for_status()
    target_path = os.path.join(target_dir, name)
    total_bytes = 0
    with open(target_path, "wb") as out:
        for chunk in resp.iter_content(chunk_size=8192):
            out.write(chunk)
            total_bytes += len(chunk)
    return target_path, total_bytes


def _process_one_file(base, act, run_folder, subfolder_name):
    """Process a single file action. Returns (base, canon, size, source) or raises."""
    action = act["action"]
    canon = act.get("canonical_name", f"{base}.xlsx")
    canon_path = os.path.join(run_folder, canon)

    if action == "DOWNLOAD":
        fm = act["sp_file"]
        orig_path, size_bytes = download_file(fm, run_folder)
        if os.path.basename(orig_path) != canon:
            os.rename(orig_path, canon_path)
        new_sync_state[base] = {
            "modified_iso": act["modified"].isoformat(),
            "subfolder": subfolder_name,
            "canonical_name": canon,
        }
        return (base, canon, size_bytes, "sharepoint")

    elif action == "REUSE":
        shutil.copy2(act["source_path"], canon_path)
        size = os.path.getsize(canon_path)
        return (base, canon, size, "reused")

    elif action == "FALLBACK":
        shutil.copy2(act["source_path"], canon_path)
        size = os.path.getsize(canon_path)
        src_short = act["source_dir"].rstrip("/").split("/")[-1]
        warnings.append(f"NOT ON SP: {base} — using fallback from {src_short} (data may be stale!)")
        return (base, canon, size, f"fallback:{src_short}")


# ---------------------------------------------------------------------------
# Check if anything actually changed
# ---------------------------------------------------------------------------
needs_work = any(a["action"] in ("DOWNLOAD", "FALLBACK") for a in actions.values())
new_sync_state = dict(prev_state)
results = []
fail_bases = []

if not needs_work:
    # ALL files unchanged — reuse existing subfolder, skip all downloads/copies
    reuse_folder = None
    for loc in prev_subfolders:
        try:
            files_in = [f.name for f in dbutils.fs.ls(loc) if not f.isDir()]
            bases_in = {canonical_base(get_canonical_name(fn)) for fn in files_in} & EXPECTED_CANONICAL
            if len(bases_in) == len(EXPECTED_CANONICAL):
                reuse_folder = loc.rstrip("/")
                break
        except Exception:
            continue

    if reuse_folder:
        subfolder_name = reuse_folder.split("/")[-1]
        run_folder = reuse_folder
        results = [(b, a.get("canonical_name", f"{b}.xlsx"), 0, "reused") for b, a in actions.items()]
        print("=" * 70)
        print(f"NO CHANGES on SharePoint — all 7 files unchanged.")
        print(f"Reusing existing folder: {subfolder_name}")
        print(f"No new subfolder created. No files downloaded or copied.")
        print("=" * 70)
    else:
        # Sync state says unchanged but no complete folder found — force download
        needs_work = True

if needs_work:
    # At least one file changed — create new timestamped subfolder
    run_ts = datetime.now(timezone.utc)
    subfolder_name = run_ts.strftime("%Y-%m-%d_%H-%M-%S")
    run_folder = os.path.join(VOLUME_BASE, subfolder_name)
    os.makedirs(run_folder, exist_ok=True)
    print(f"Target: {run_folder}")
    print("=" * 70)

    for base in sorted(EXPECTED_CANONICAL):
        act = actions[base]
        action = act["action"]
        try:
            result = _process_one_file(base, act, run_folder, subfolder_name)
            results.append(result)
            _, canon, size, source = result
            size_str = f"{size/1024:.0f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
            icon = {"sharepoint": "\U0001f7e2 DOWNLOAD ", "reused": "\u26aa REUSE    "}.get(source, "\U0001f7e0 FALLBACK ")
            src_label = "<- SharePoint" if source == "sharepoint" else f"<- prev ({source.split(':')[-1] if ':' in source else 'unchanged'})" 
            print(f"  {icon} {base:42s} {size_str:>10s}  {src_label}")
        except Exception as e:
            # Primary action failed — try recovery from previous subfolder
            recovered = find_in_subfolders(base, prev_subfolders + fallback_extras)
            if recovered:
                src_path, src_name, src_dir = recovered
                canon = act.get("canonical_name", f"{base}{os.path.splitext(src_name)[1]}")
                canon_path = os.path.join(run_folder, canon)
                try:
                    shutil.copy2(src_path, canon_path)
                    size = os.path.getsize(canon_path)
                    results.append((base, canon, size, f"recovered:{src_dir.rstrip('/').split('/')[-1]}"))
                    src_short = src_dir.rstrip("/").split("/")[-1]
                    warnings.append(f"{action} failed for {base}: {e}. Recovered from {src_short}.")
                    print(f"  \U0001f7e0 RECOVERED {base:42s} {size/1024:.0f} KB  <- {src_short}")
                except Exception as e2:
                    fail_bases.append(base)
                    print(f"  \u274c FAILED    {base:42s} {e2}")
            else:
                fail_bases.append(base)
                print(f"  \u274c FAILED    {base:42s} {e}")

    print("=" * 70)

    if fail_bases:
        msg = f"FATAL: {len(fail_bases)} file(s) could not be obtained:\n" + "\n".join(f"  - {b}" for b in sorted(fail_bases))
        print(f"\n{msg}")
        raise FileNotFoundError(msg)

# --- Save sync state ---
try:
    with open(SYNC_STATE_FILE, "w") as fh:
        _json.dump(new_sync_state, fh, indent=2, default=str)
    print(f"Sync state saved.")
except Exception as e:
    print(f"WARNING: Could not save sync state: {e}")

# --- Counts for Summary cell ---
n_dl = sum(1 for r in results if r[3] == "sharepoint")
n_re = sum(1 for r in results if r[3] == "reused")
n_fb = sum(1 for r in results if r[3].startswith("fallback"))
n_rc = sum(1 for r in results if r[3].startswith("recovered"))
print(f"\nResult: {len(results)}/{len(EXPECTED_CANONICAL)} files ready")
print(f"  \U0001f7e2 Downloaded:  {n_dl}")
print(f"  \u26aa Reused:      {n_re}")
print(f"  \U0001f7e0 Fallback:    {n_fb}")
if n_rc:
    print(f"  \U0001f7e0 Recovered:   {n_rc}")

# COMMAND ----------

# DBTITLE 1,Summary & Exit
# ---------------------------------------------------------------------------
# Final summary and pass run_folder to downstream notebooks
# ---------------------------------------------------------------------------
print("\nSync history (most recent first):")
try:
    entries = dbutils.fs.ls(VOLUME_BASE)
    folders = sorted([e.name.rstrip("/") for e in entries if e.isDir()], reverse=True)
    for i, folder in enumerate(folders[:10]):
        marker = "  <-- THIS RUN" if folder == subfolder_name else ""
        try:
            sub_files = [f.name for f in dbutils.fs.ls(f"{VOLUME_BASE}/{folder}") if not f.isDir()]
            print(f"  {folder}  ({len(sub_files)} files){marker}")
        except Exception:
            print(f"  {folder}  (?){marker}")
except Exception:
    print(f"  {subfolder_name}  (current run)")

if warnings:
    print(f"\n{'='*70}")
    print(f"\u26a0 {len(warnings)} WARNING(S):")
    for w in warnings:
        print(f"  - {w}")
    print(f"{'='*70}")

print(f"\nRun folder: {run_folder}")

# Build per-file source summary for exit JSON
file_sources = {}
for base, canon, size, source in results:
    file_sources[base] = source

print(f"\n\u2705 Sync complete: {n_dl} downloaded + {n_re} reused + {n_fb} fallback = {len(results)} files")
if n_re:
    print(f"   {n_re} file(s) unchanged on SharePoint — reused from previous run (no download needed).")
if n_fb:
    print(f"   {n_fb} file(s) not on SharePoint — using fallback from previous run (data may be stale).")
print("   Next step: run 01_bronze_ingestion")

# Pass run_folder to downstream tasks in multi-task job setup
try:
    dbutils.jobs.taskValues.set(key="run_folder", value=run_folder)
except Exception:
    pass  # Not running as a job task — ignore

dbutils.notebook.exit(json.dumps({
    "run_folder": run_folder,
    "subfolder": subfolder_name,
    "files": len(results),
    "downloaded": n_dl,
    "reused": n_re,
    "fallback": n_fb,
    "warnings": len(warnings),
    "file_sources": file_sources,
}))
