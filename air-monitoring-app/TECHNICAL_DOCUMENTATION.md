# Air Monitoring App — Technical Documentation

**Repo**: https://dev.azure.com/etexit/Etex%20Portfolio%202.0/_git/DS-Air-Monitoring-App  
**Owner**: Arda Bicakci (mustafaarda.bicakci@etexgroup.com)  
**Last Updated**: July 2026

---


## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           DATABRICKS APP (Streamlit)                             │
│                                                                                 │
│   ┌──────────┐  ┌───────────────┐  ┌──────────────┐  ┌─────────────┐           │
│   │  Upload  │  │ Output Browser│  │Upload History│  │  Analytics  │           │
│   └────┬─────┘  └───────┬───────┘  └──────┬───────┘  └──────┬──────┘           │
│        │                │                  │                 │                  │
│        ▼                ▼                  ▼                 ▼                  │
│   ┌─────────────────────────────────────────────────────────────────┐           │
│   │                    utils/db_utils.py                            │           │
│   │         SQL Warehouse Connection (databricks-sql-connector)     │           │
│   └──────────────────────────────┬──────────────────────────────────┘           │
└──────────────────────────────────┼──────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           UNITY CATALOG                                          │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────┐               │
│   │  general_{d|a|p}.air_monitoring_v2                          │               │
│   │     ├── output_table    (sample results, 30 cols)           │               │
│   │     ├── sites           (site config + access control)      │               │
│   │     └── upload_log      (audit trail)                       │               │
│   └─────────────────────────────────────────────────────────────┘               │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────┐               │
│   │  general_{d|a|p}.air_monitoring (VOLUME)                    │               │
│   │     └── uploaded_reports/{site_code}/{timestamp}_{file}.pdf  │               │
│   └─────────────────────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐       ┌─────────────────────────────────┐
│  Azure Document         │       │  Azure OpenAI (GPT-4)           │
│  Intelligence           │       │  Structured extraction from     │
│  PDF → raw tables/text  │       │  document content               │
└─────────────────────────┘       └─────────────────────────────────┘
```

---

## 2. Repository Structure

```
DS-Air-Monitoring-App/
├── databricks.yml                    # DAB bundle definition (for Foundations template)
├── src/                              # App source — deployed as-is to each environment
│   ├── app.py                        # Streamlit main (all 4 tabs)
│   ├── app.yaml                      # Default app.yaml (TEST env, for direct Git deploy)
│   ├── requirements.txt              # Python dependencies
│   ├── etex_logo.jpeg                # Branding asset
│   └── utils/
│       ├── __init__.py
│       ├── config.py                 # Environment-aware config (reads env vars)
│       ├── db_utils.py               # SQL Warehouse connection, CRUD, dedup
│       ├── doc_intelligence.py       # Azure Document Intelligence wrapper
│       └── llm_processor.py          # GPT extraction + Analysis_method normalization
│
├── config/                           # Environment-specific app.yaml files
│   ├── app.test.yaml                 # DEV workspace (automation_d)
│   ├── app.acc.yaml                  # ACC workspace (automation_a)
│   └── app.prd.yaml                  # PRD workspace (automation_p)
│
├── scripts/
│   ├── deploy_app.sh                 # App deployment script (auth + upload + deploy)
│   └── setup_tables.py              # Table provisioning + Excel migration (idempotent)
│
├── test/                             # DAB resources (deployed via bundle by Foundations)
│   ├── resources/
│   │   └── air_monitoring_setup.job.yml  # Table setup job definition
│   └── src/
│       └── setup_tables.py          # Copy of scripts/setup_tables.py for bundle
│
├── pipelines/                        # Azure DevOps pipeline definitions
│   ├── Deploy_App_TEST.yml
│   ├── Deploy_App_ACC.yml           # Triggers on push to Feature/Test
│   ├── Deploy_App_PRD.yml           # Triggers on merge to main
│   └── variables/
│       ├── app_variables_test.yml
│       ├── app_variables_acc.yml
│       └── app_variables_prd.yml
│
├── README.md                         # Project overview
└── TECHNICAL_DOCUMENTATION.md        # This file
```

---

## 3. Data Model

### 3.1 output_table

Main fact table — one row per extracted sample measurement.

| Column | Type | Description |
|--------|------|-------------|
| row_id | STRING | UUID — unique per row, enables safe UPDATE |
| Site_name | STRING | Plant/site name |
| Code | STRING | Site code (e.g. "9010_03", "7000") |
| Site_Address | STRING | Physical address |
| upload_date | TIMESTAMP | When the PDF was processed |
| Document_name | STRING | Original PDF filename |
| Report_number | STRING | Lab report number |
| Sample_no | STRING | Unique sample identifier |
| Pump_Location | STRING | Where the air sample was taken |
| Lab_name | STRING | Laboratory that performed analysis |
| Project_Name | STRING | Project context |
| Building | STRING | Building/factory identifier |
| Sample_Date | STRING | Date sample was collected (DD/MM/YYYY) |
| Analysis_method | STRING | "Optical Microscopy" or "Electron Microscopy" (normalized) |
| Followed_Norm | STRING | Standard followed (NIOSH 7402, ISO 16000-7, etc.) |
| Volume | STRING | Air volume sampled (litres) |
| Concentration_result | STRING | Fibre concentration (preserves "<" prefix) |
| Concentration_unit | STRING | Unit (f/ml, f/L, fibres/cm3, etc.) |
| Concentration_result_in_f_ml | STRING | Normalized to fibres/ml for cross-comparison |
| Flag_EM_Concentration | DOUBLE | 1.0 if Electron Microscopy, else 0.0 |
| Flag_High_Concentration | BOOLEAN | True if > 0.01 f/ml |
| PDF_URL | STRING | Volume path to stored PDF |
| row_status | STRING | "active", "modified", or "removed" |
| removal_reason | STRING | Why removed: "Duplicate", "Personal sample", "Manually deleted" |
| status_updated_at | TIMESTAMP | Last status change |
| uploaded_by | STRING | User email who uploaded |
| upload_batch_id | STRING | UUID grouping files from same upload session |
| modified_by | STRING | User email who last edited |
| Frozen_Docs | STRING | Legacy V1 field (hidden in app) |
| Delete_docs | STRING | Legacy V1 field (hidden in app) |

**Deduplication grain**: `Code + Sample_no + Sample_Date + Volume + Concentration_result`

### 3.2 sites

Site configuration and access control.

| Column | Type | Description |
|--------|------|-------------|
| site_name | STRING | Display name (e.g. "Tisselt") |
| site_code | STRING | Unique code (e.g. "6000") |
| address | STRING | Physical address |
| allowed_users | STRING | Email addresses separated by `/` |

**Access control mechanism**: App reads `allowed_users`, splits by `/`, and filters all queries to only show data for sites where current user's email appears in the list.

### 3.3 upload_log

Audit trail for all upload events.

| Column | Type | Description |
|--------|------|-------------|
| upload_id | STRING | UUID per upload event |
| batch_id | STRING | Groups multiple files uploaded in same session |
| filename | STRING | PDF filename |
| site_code | STRING | Target site |
| site_name | STRING | Target site name |
| uploaded_by | STRING | User email |
| upload_time | TIMESTAMP | When uploaded |
| num_records | INT | Total samples extracted from PDF |
| num_duplicates_found | INT | How many matched existing records |
| num_saved | INT | How many actually saved |
| status | STRING | "success" or error description |
| volume_path | STRING | Where PDF is stored in volume |

---

## 4. Processing Pipeline (Upload Flow)

```
User selects site → Uploads PDF(s)
       │
       ▼
┌──────────────────────────┐
│ 1. Upload to Volume      │  utils/db_utils.py → upload_file_to_volume()
│    /Volumes/.../          │  Pattern: {YYYYMMDD_HHMMSS}_{filename}
│    {site_code}/{file}     │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 2. Document Intelligence │  utils/doc_intelligence.py → extract_from_pdf()
│    PDF → tables + text   │  Azure AI Document Intelligence (prebuilt-layout)
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 3. GPT Extraction        │  utils/llm_processor.py → parse_extraction()
│    Content → JSON array  │  Azure OpenAI GPT-4, temp=0.1, max 3 retries
│    of sample records     │  Prompt enforces: "Optical" or "Electron" only
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 4. Post-Processing       │  In app.py upload flow:
│    - Normalize method    │  • _normalize_analysis_method() (multi-language)
│    - Detect personal     │  • Pump_Location keyword match → auto-remove
│    - Convert units       │  • convert_concentration_to_f_ml()
│    - Flag high conc.     │  • > 0.01 f/ml → Flag_High_Concentration
│    - Check duplicates    │  • check_duplicates() on DEDUP_GRAIN
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 5. User Review           │  Side-by-side: PDF preview | editable table
│    Include/exclude rows  │  User can toggle Include, see duplicate warnings
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 6. Save                  │  write_to_output_table() — batch INSERT
│    + Log upload event    │  log_upload() — audit trail
│    + Mark duplicates     │  Duplicates saved as row_status='removed'
└──────────────────────────┘
```

---

## 5. Row Status Lifecycle

```
                    ┌─────────────┐
     Upload ───────►│   active    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         User edits   User removes   Auto-detected
         data fields   manually      (personal/dup)
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ modified │ │ removed  │ │ removed  │
        └──────────┘ └──────────┘ └──────────┘
                           │
                     User restores
                           │
                           ▼
                    ┌─────────────┐
                    │   active    │  (removal_reason cleared)
                    └─────────────┘
```

**Removal reasons** (stored in `removal_reason` column):
- `Duplicate` — matched existing record on dedup grain
- `Personal sample` — Pump_Location contains personal/personnel/personeel/personale/individuel
- `Manually deleted` — user set status to "removed" in Output Browser

---

## 6. Analysis Method Normalization

GPT sometimes returns non-English method names. `_normalize_analysis_method()` in `llm_processor.py` handles this:

| Input variants (any language) | Normalized output |
|-------------------------------|-------------------|
| Transmission Electron Microscopy, Microscopie Électronique à Transmission Analytique, META, TEM, SEM, Elektronenmikroskopie | **Electron Microscopy** |
| Phase Contrast Microscopy, Microscopie Optique, MOCP, PCM, Lichtmikroskopie, Fasecontrastmicroscopie | **Optical Microscopy** |
| Anything else unrecognized | NULL (shows as "Not specified") |

Fuzzy fallback: if no exact match, keywords like "electr/électr/elektr" → Electron, "opti/phase/contrast" → Optical.

---

## 7. Environment Configuration

### 7.1 Multi-Environment Strategy

Same source code runs in all environments. Only `app.yaml` differs.

| Setting | TEST (dev) | ACC | PRD |
|---------|-----------|-----|-----|
| Workspace | adb-7181820732839861 | adb-4796304964978539 | adb-4844910598668398 |
| Catalog | general_d | general_a | general_p |
| Schema | air_monitoring_v2 | air_monitoring_v2 | air_monitoring_v2 |
| Volume schema | air_monitoring | air_monitoring | air_monitoring |
| App name | air-monitoring-v2 | air-monitoring-app | air-monitoring-app |
| Warehouse | 69ada62b2fb9b9e2 | fe5f9b40ac3a9b6e | 83294e3f6b44f138 |

### 7.2 config.py Pattern

```python
import os
UNITY_CATALOG = os.environ.get("UNITY_CATALOG", "general_d")
SCHEMA = os.environ.get("SCHEMA", "air_monitoring_v2")
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
```

Defaults point to DEV — for local development or running without app.yaml.

### 7.3 app.yaml Structure

```yaml
command:
  - streamlit
  - run
  - app.py
  - --server.port
  - "8000"
  - --server.address
  - "0.0.0.0"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    value: "<warehouse-id>"
  - name: UNITY_CATALOG
    value: "general_<env>"
  - name: SCHEMA
    value: "air_monitoring_v2"
  - name: VOLUME_SCHEMA
    value: "air_monitoring"
  - name: VOLUME_NAME
    value: "uploaded_reports"

resources:
  - name: "sql-warehouse"
    sql_warehouse:
      id: "<warehouse-id>"
      permission: "CAN_USE"
```

---

## 8. CI/CD Pipeline

### 8.1 Deployment Flow

```
Feature/Test ──push──► ACC pipeline (auto) ──► deploys bundle + app to ACC workspace
     │
     └──PR──► merge to main ──► PRD pipeline (auto) ──► deploys to PRD workspace
```

### 8.1.1 Pipeline Architecture (Foundations Template)

Uses `da-mdp-foundations-deployments` shared template (same as DS-cicd-Lead-Time-AI):

```yaml
resources:
  repositories:
    - repository: da-mdp-foundations-deployments
      type: git
      name: da-mdp-foundations-deployments    # NO project prefix!
      ref: refs/heads/main

stages:
  - template: pipelines/templates/deploy_databricks.yml@da-mdp-foundations-deployments
    parameters:
      env: ${{ variables.PIPELINE_ENV }}
      envLong: ${{ variables.ENV_LONG }}
      subscriptionName: ${{ variables.SUBSCRIPTION_NAME }}
      keyVaultName: ${{ variables.KEYVAULT_NAME }}
      ...
```

Template handles: Key Vault secrets → CLI install → SPN auth → Bundle validate → Bundle deploy → Push acc branch.

### 8.1.2 Table Provisioning & Data Migration

Idempotent script for setting up tables and migrating data from V1 Excel exports.

**Migration path (per environment):**
```
/Volumes/{catalog}/bronze/bronze_volume/air_monitoring/migration/
├── Output_Table.xlsx     # V1 full export (7939 rows, 23 columns)
└── sites.xlsx            # Site dimension (53 rows, 4 columns)
```

#### Excel vs Delta Schema Difference

The V1 Excel export has 23 columns. The V2 Delta table has 30 columns.
7 columns are ADDED during migration:

| Column | Source | Value |
|--------|--------|-------|
| row_id | Generated | UUID4 (unique per row) |
| row_status | Derived | 'active' or 'removed' (from Frozen_Docs='x') |
| removal_reason | Derived | 'V1 frozen document' if removed |
| status_updated_at | NULL | Set by app on future edits |
| uploaded_by | Set | 'migrated' |
| upload_batch_id | Set | 'excel_migration_YYYYMMDD_HHMMSS' |
| modified_by | NULL | Set by app on future edits |

#### Data Transformations

| Field | Excel | Delta | Transformation |
|-------|-------|-------|----------------|
| Sample_Date | `datetime64` (2026-07-01) | STRING | → `strftime('%d-%b-%Y')` → '01-Jul-2026' |
| Frozen_Docs | 'x' or empty | STRING | Kept as-is; used to derive row_status |
| Delete_docs | float NaN | STRING | → None |
| PDF_URL | SharePoint URLs | STRING | Kept as-is (PDFs not migrated to Volume) |
| Flag_EM_Concentration | float | DOUBLE | Direct mapping |
| Flag_High_Concentration | bool | BOOLEAN | Direct mapping |

#### Matching Strategy: LEFT ANTI JOIN

Uses **expanded grain** for matching:
```
Code + Sample_no + Sample_Date + Volume + Concentration_result + Document_name
```

**Why LEFT ANTI JOIN instead of MERGE?**
- Delta has legitimate duplicate grain keys (same measurement uploaded twice,
  one active + one marked removed by app's dedup mechanism)
- MERGE would fail: "multiple target rows match one source row"
- Anti-join simply checks existence: row in Excel but NOT in Delta → INSERT

**Why expanded grain (6 columns) instead of app's dedup grain (5 columns)?**
- App dedup grain: Code + Sample_no + Sample_Date + Volume + Concentration_result
- Problem: 328 duplicate grain keys in Delta (same sample from multiple PDFs)
- Adding Document_name makes Excel rows uniquely identifiable (0 Excel duplicates)

#### Behavior Matrix

| Scenario | Sites | Output | Upload_log |
|----------|-------|--------|------------|
| First time (empty tables) | Full INSERT | Full INSERT (generate row_ids) | Untouched |
| Incremental (fresh Excel) | UPSERT on site_code | Anti-join → INSERT only new | Untouched |
| Re-run (same Excel) | No-op (all match) | 0 new rows (idempotent) | Untouched |
| Row exists + modified by user | N/A | PRESERVED (never overwritten) | N/A |
| Row exists + marked removed | N/A | PRESERVED (never resurrected) | N/A |

#### Concurrent Usage Scenario (V1 + V2 running simultaneously)

```
V1 (SharePoint) ──export──► Output_Table.xlsx ──upload──► Volume/migration/
                                                              │
V2 (Databricks)  ←──── setup_tables.py reads Excel ──────────┘
      │                        │
      │ App creates new rows   │ Script inserts only net-new
      │ with row_ids           │ rows (no collision)
      ▼                        ▼
  Delta table: existing rows NEVER touched by script
```

**Usage:** `python scripts/setup_tables.py automation_a`

Deployed as DAB job via Foundations template → trigger from Databricks Jobs UI.

### 8.2 Deploy Script (scripts/deploy_app.sh)

```bash
# Usage: ./scripts/deploy_app.sh <env> <app-name>
# Example: ./scripts/deploy_app.sh acc air-monitoring-app

1. Upload src/ → /Workspace/automation/air-monitoring-app/<env>/
2. Copy config/app.<env>.yaml → target/app.yaml
3. databricks apps deploy <app-name> --source-code-path <target-path>
4. Verify: databricks apps get <app-name> → check status = RUNNING
```

### 8.3 Pipeline Authentication

Same pattern as all DS-cicd-* projects:
- Azure Key Vault secrets → SPN credentials + workspace hostname
- Service connections: `etex.spoke.mdp.automation.azdevops.{dev,acc,prd}`
- Key Vaults: `WE-SPOKE-MDP-FDN-{T,A,P}-KV` (infra secrets)
- Future: `WE-SPOKE-MDP-AUT-{T,A,P}-KV` (app-specific secrets: OpenAI, Doc Intelligence)

### 8.5 Branch Strategy

| Branch | Purpose | Pipeline Trigger |
|--------|---------|-----------------|
| `Feature/Test` | Development | ACC auto-deploy on push |
| `acc` (lowercase!) | Tracks what's deployed to ACC | Managed by Foundations template |
| `main` | Production code | PRD auto-deploy on merge |

**CRITICAL:** `acc` branch must be lowercase. Foundations template derives branch name from `ENV_LONG` variable.

### 8.6 Build Service Permissions (Required!)

Azure DevOps → Project Settings → Repos → `DS-Air-Monitoring-App` → Security:
- Find `Etex Portfolio 2.0 Build Service (etexit)`
- Set ALL permissions to **explicit Allow** (inherited is NOT sufficient):
  - Contribute, Bypass policies when pushing, Create branch, Force push, Read

### 8.4 Key Difference from Job CI/CD

| Aspect | Job CI/CD (DS-cicd-Air-Monitoring) | App CI/CD (this repo) |
|--------|--------------------------------------|------------------------|
| Tool | `databricks bundle deploy --target T` | `databricks apps deploy <name> --source-code-path <path>` |
| Config | `databricks.yml` with targets | `app.yaml` per environment |
| Trigger | Bundle deploy + job schedule | Source upload + app deploy (always-on) |
| Runtime | Cluster (on-demand) | App compute (persistent) |

---

## 9. External Services

### 9.1 Azure Document Intelligence

- **Endpoint**: `https://we-spoke-mdp-t-formrecogniser.cognitiveservices.azure.com/`
- **Model**: `prebuilt-layout` (tables + paragraphs extraction)
- **Input**: PDF binary bytes
- **Output**: `{ paragraphs: [...], tables: [...] }`
- **Note**: Key currently hardcoded in config. Should move to Databricks secrets for ACC/PRD.

### 9.2 Azure OpenAI

- **Endpoint**: `https://musta-m830len4-eastus2.cognitiveservices.azure.com/`
- **Model**: `EPD_Pulse_gpt-5.4` (GPT-4 deployment)
- **Temperature**: 0.1 (deterministic extraction)
- **Max tokens**: 4000
- **Response format**: JSON object
- **Retry**: 3 attempts on failure
- **Note**: Key currently hardcoded. Move to secrets for production.

---

## 10. PDF Storage & Preview

### Volume Structure

```
/Volumes/general_{env}/air_monitoring/uploaded_reports/
├── 10002/
│   ├── 20240805_000000_10002_AR-24-VL-01036831-01.pdf
│   └── 20240903_000000_10002_AR-24-VL-01045639-01.pdf
├── 6000/
│   ├── 20260604_000000_6000_260604_Etex_bormstraat_24.pdf
│   └── ...
└── 9010_03/
    └── ...
```

**Naming convention**: `{YYYYMMDD}_{HHMMSS}_{original_filename}`

### PDF Preview Mechanism

The Output Browser uses SQL `read_files()` to load PDF binary from volume:

```sql
SELECT content FROM read_files('<volume_path>', format => 'binaryFile') LIMIT 1
```

The binary is base64-encoded and rendered in an iframe:
```html
<iframe src="data:application/pdf;base64,{b64_content}" />
```

---

## 11. Access Control

### How It Works

1. App gets current user: `ctx = st.context` → user email
2. Queries `sites` table for rows where `allowed_users` contains the email
3. Extracts `site_code` list for that user
4. ALL data queries append: `WHERE Code IN ({allowed_codes})`

### Managing Access

Edit `sites.allowed_users` column — emails separated by `/`:
```
pascal.journet@etexgroup.com/chiara.senzolo@etexgroup.com/sofie.staes@etexgroup.com
```

Admin users (appear in all sites): chiara.senzolo, sofie.staes, mustafaarda.bicakci, mikail.malcikan

---

## 12. SQL Warehouse Connection

```python
# db_utils.py connection pattern
from databricks import sql as databricks_sql
from databricks.sdk.core import Config

def get_connection():
    cfg = Config()  # Auto-discovers app service principal credentials
    host = cfg.host.replace("https://", "")
    return databricks_sql.connect(
        server_hostname=host,
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
        credentials_provider=lambda: cfg.authenticate,
    )
```

The app runs as a service principal — authentication is automatic via Databricks SDK.

---

## 13. Dependencies

```
streamlit==1.40.0
databricks-sdk>=0.30.0
databricks-sql-connector>=3.0.0
azure-ai-documentintelligence>=1.0.0b2
azure-core>=1.30.0
openai>=1.0.0
pandas>=2.0.0
openpyxl>=3.1.0
xlsxwriter>=3.1.0
python-dateutil>=2.8.0
```

---

## 14. Known Limitations & TODOs

| Item | Priority | Status |
|------|----------|--------|
| Move API keys to Databricks secrets / Key Vault | HIGH | TODO for ACC/PRD |
| ACC/PRD SQL Warehouse IDs | HIGH | ✅ DONE — ACC=fe5f9b40ac3a9b6e, PRD=83294e3f6b44f138 |
| SPN needs CAN_MANAGE on app in ACC/PRD | HIGH | TODO — verify permissions |
| Volume permissions for SPN in ACC/PRD | MEDIUM | TODO |
| 6 unmatched PDF_URLs (SharePoint) still in output_table | LOW | 9 rows with old SharePoint URLs |
| `Delete_docs` and `Frozen_Docs` columns are legacy | LOW | Hidden in app, kept for backward compatibility |
| Secrets hardcoded as fallback defaults in config.py | MEDIUM | Move to env vars or secrets scope |

---

## 15. Relationship to V1 Pipeline (DS-cicd-Air-Monitoring)

| Component | V1 (job-based) | V2 (app-based) |
|-----------|----------------|----------------|
| Repo | `DS-cicd-Air-Monitoring` | `DS-Air-Monitoring-App` |
| Schema | `general_d.air_monitoring` | `general_d.air_monitoring_v2` |
| Volume | `air_monitoring.uploaded_reports` | Same volume (shared) |
| Processing | Scheduled job crawls SharePoint | User uploads PDF in app |
| Output | `output_table` (26 cols) | `output_table` (30 cols, +row_id, uploaded_by, etc.) |
| Sites | `sites` (7 cols, V1 naming) | `sites` (4 cols, clean naming + access control) |
| Status field | deleted_x / personal / duplicate / active | active / modified / removed |

V2 uses V1's **volume** for PDF storage. V1's SharePoint crawling pipeline can continue to run independently — data doesn't conflict because they write to different schemas.

---

## 16. Quick Reference Commands

```bash
# Check app status
databricks apps get air-monitoring-v2 --output JSON

# View app logs
databricks apps logs air-monitoring-v2

# Manual deploy (dev)
bash scripts/deploy_app.sh test air-monitoring-v2

# Restart app
databricks apps stop air-monitoring-v2
databricks apps start air-monitoring-v2

# Check deployment history
databricks apps list-deployments air-monitoring-v2 --output JSON
```

---

## 17. Contact

- **Developer**: Arda Bicakci (mustafaarda.bicakci@etexgroup.com)
- **Team**: Mikail Malcikan (mikail.malcikan@etexgroup.com)
- **Stakeholders**: Chiara Senzolo, Sofie Staes
- **Infrastructure**: Mindaugas Mazelis (CI/CD, workspace setup)
