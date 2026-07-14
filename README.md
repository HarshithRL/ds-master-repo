# Data Science Master Repository


Single shared repository for all Data Science projects at Etex. Each project is an **independent Databricks Asset Bundle** (its own `databricks.yml`, resources, and source code) living in a top-level folder — deployed by **one shared CI/CD pipeline** (Azure DevOps). No need to create a new repo, configure new pipelines, or request new permissions for each project.

---

## Why a Single Repo?

Setting up CI/CD per project is inefficient:
- Permission requests for each new repo and pipeline
- Duplicated pipeline YAMLs and variable groups
- Inconsistent configurations across projects

This repo solves that by providing:

1. **One Azure DevOps pipeline** that iterates over all project bundles and deploys them (TEST / ACC / PRD)
2. **Independent DAB per project** — each project owns its own `databricks.yml`, job definitions, and notebooks
3. **Shared environment variable files** for each deployment stage
4. **A working example project** (`hello-world/`) to copy when starting a new project
5. **AI agent guidance** (`.md` files) so assistants can help onboard new projects

---

## Data Architecture — Medallion Pattern

All projects follow a **Bronze → Silver → Gold** layered architecture within Unity Catalog:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│       BRONZE        │────▶│       SILVER        │────▶│        GOLD         │
│                     │     │                     │     │                     │
│ • Raw ingested data │     │ • Cleaned & filtered│     │ • ML predictions    │
│ • Minimal transform │     │ • Enriched fields   │     │ • KPI calculations  │
│ • Source snapshot   │     │ • Deduplicated      │     │ • Business rollups  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### Schema Structure per Environment

| Layer | Schema Pattern | Example (automation catalog) |
|-------|---------------|------------------------------|
| Bronze | `{catalog}.bronze` | `automation_d.bronze` |
| Silver | `{catalog}.silver` | `automation_d.silver` |
| Gold | `{catalog}.gold` | `automation_d.gold` |

### Table Naming Convention

```
{catalog}.{layer}.{project}_{description}
```

Examples:
- `automation_d.bronze.hello_world_raw`
- `automation_d.silver.hello_world_clean`
- `automation_d.gold.hello_world_summary`

---

## Repository Structure

```
DS-Master-Repo/
│
├── README.md                                   # This file
├── CICD_SETUP_GUIDE.md                         # Full CI/CD setup walkthrough
├── .assistant_instructions.md                  # AI agent instructions for setup guidance
│
├── pipelines/                                  # Azure DevOps pipeline YAMLs (shared)
│   ├── Automation_Deploy_Databricks_TEST.yml
│   ├── Automation_Deploy_Databricks_ACC.yml
│   ├── Automation_Deploy_Databricks_PRD.yml
│   └── variables/                              # Environment-specific variables
│       ├── databricks_variables_test.yml
│       ├── databricks_variables_acc.yml
│       └── databricks_variables_prd.yml
│
├── hello-world/                                # EXAMPLE project — fully working DAB
│   ├── databricks.yml                          # Bundle definition for this project
│   ├── resources/
│   │   └── hello_world.job.yml                 # Job definition (Bronze → Silver → Gold)
│   └── src/
│       └── notebooks/
│           ├── config_file.py                  # Environment detection + medallion helpers
│           ├── 01_bronze_ingest.py             # Bronze: write raw data
│           ├── 02_silver_transform.py          # Silver: clean + enrich
│           └── 03_gold_aggregate.py            # Gold: business-ready output
│
└── <your-project>/                             # ← Add your project here (same structure)
    ├── databricks.yml
    ├── resources/
    │   └── <your_project>.job.yml
    └── src/
        └── notebooks/
            └── ...
```

Each top-level folder with a `databricks.yml` is an independent bundle. The CI/CD pipeline discovers and deploys all of them.

---

## How to Add a New Project

You do **not** create a new repo. You add a new folder to this one:

1. **Copy the example project:**
   ```
   cp -r hello-world/ my-new-project/
   ```

2. **Edit `databricks.yml`:**
   - Change the bundle name to your project name
   - Adjust workspace paths and catalog references if needed

3. **Edit `resources/<project>.job.yml`:**
   - Rename the job
   - Update notebook paths, schedule, and cluster config

4. **Replace the notebooks** in `src/notebooks/` with your own:
   - Keep `config_file.py` (or adapt it)
   - Follow `01_Bronze_*`, `02_Silver_*`, `03_Gold_*` naming

5. **Push to the repo** — the existing CI/CD pipeline picks up your bundle automatically:
   ```
   feature branch → TEST (manual) → PR → ACC (automatic) → merge → PRD (automatic)
   ```

No new pipeline setup. No new permissions. No new repo.

---

## Bundle Targets (per project)

Each project's `databricks.yml` defines four targets:

| Target | Workspace | Catalog Pattern | Workspace Path |
|--------|-----------|-----------------|----------------|
| D (development) | `adb-7181820732839861` | `<prefix>_d` | Per-user personal path |
| T (test / CI) | `adb-7181820732839861` | `<prefix>_d` | `/Workspace/ds/{bundle}` |
| A (acceptance) | `adb-4796304964978539` | `<prefix>_a` | `/Workspace/ds/{bundle}` |
| P (production) | `adb-4844910598668398` | `<prefix>_p` | `/Workspace/ds/{bundle}` |

Schemas per layer: `.bronze` / `.silver` / `.gold`

---

## Notebook Pattern

Every notebook starts with:
```python
# MAGIC %run ./config_file
```

Then uses the layer helpers:
```python
# Bronze notebook — write raw data
df.write.mode("overwrite").saveAsTable(bronze_table("my_project_raw"))

# Silver notebook — read bronze, write silver
df = spark.read.table(bronze_table("my_project_raw"))
df_clean.write.mode("overwrite").saveAsTable(silver_table("my_project_clean"))

# Gold notebook — read silver, write gold
df = spark.read.table(silver_table("my_project_clean"))
predictions.write.mode("overwrite").saveAsTable(gold_table("my_project_predictions"))
```

---

## Key References

- Shared deployment template: `da-mdp-foundations-deployments` (Modern data platform project)
- Sibling platform repo: `da-mdp-foundations-databricks` (same architecture, platform services)
- Azure DevOps org: `etexit`
- Azure DevOps project: `Etex Portfolio 2.0`
- Databricks Asset Bundles docs: https://docs.databricks.com/dev-tools/bundles/index.html

---

## Contacts

| Name | Email |
|------|-------|
| Pierre de Laguiche | pierre.delaguiche@etexgroup.com |
| Mustafa Arda Bicakci | mustafaarda.bicakci@etexgroup.com |
