# CI/CD Setup Guide — DS-Master-Repo

Step-by-step guide for the one-time repo setup and for adding new DS projects.

---

## Quick Start (TL;DR)

**One-time setup (already done):**
1. Repo exists in Azure DevOps (`Etex Portfolio 2.0` project)
2. 3 pipelines created (TEST, ACC, PRD) pointing to `pipelines/*.yml`
3. Environments, permissions, and build validation configured

**Adding a new project:**
1. Copy `hello-world/` → `<your-project>/`
2. Edit `<your-project>/databricks.yml` → change bundle name, catalog prefix
3. Edit `<your-project>/resources/*.job.yml` → rename job, update notebook paths and schedule
4. Edit `<your-project>/src/notebooks/config_file.py` → change catalog prefix
5. Add your notebooks to `<your-project>/src/notebooks/`
6. Push → existing CI/CD pipeline deploys automatically

---

## 1. Prerequisites

Before you start:

- [ ] Access to Azure DevOps project `Etex Portfolio 2.0` (org: `etexit`)
- [ ] Service connections provisioned:
  - `etex.spoke.mdp.automation.azdevops.dev` (TEST)
  - `etex.spoke.mdp.automation.azdevops.acc` (ACC)
  - `etex.spoke.mdp.automation.azdevops.prd` (PRD)
- [ ] Key Vault access:
  - `WE-SPOKE-MDP-FDN-T-KV` (TEST)
  - `WE-SPOKE-MDP-FDN-A-KV` (ACC)
  - `WE-SPOKE-MDP-FDN-P-KV` (PRD)
- [ ] Secrets in Key Vaults:
  - `etex-spoke-mdp-automation-devops-{dev,acc,prd}-id` (SPN App ID)
  - `etex-spoke-mdp-automation-devops-{dev,acc,prd}-secret` (SPN Secret)
  - `etex-tenant-id` (Azure Tenant ID)
  - `etex-spoke-mdp-adb-{t,a,p}-hostname` (Databricks hostname)
- [ ] Access to `da-mdp-foundations-deployments` shared repo
- [ ] Access to Databricks workspaces (dev, acc, prd)

> If service connections or Key Vault access is missing, raise a ticket with the Hosting team.

---

## 2. One-Time Repo Setup (Already Done)

This section documents what was done to create the repo. You do NOT repeat this.

### 2a. Azure DevOps Repo

1. Repo created in Azure DevOps → **Etex Portfolio 2.0** → **Repos**
2. Name: `DS-Master-Repo`
3. Initial commit with this content pushed to `main`

### 2b. Connect Databricks to the Repo

1. In Databricks → **Workspace** → your user folder
2. **Create** → **Git Folder**
3. Git repo URL: `https://dev.azure.com/etexit/Etex%20Portfolio%202.0/_git/DS-Master-Repo`
4. Git provider: Azure DevOps Services

> **Warning:** The project is `Etex Portfolio 2.0` (with spaces). In URLs: `Etex%20Portfolio%202.0`. Do NOT use `Etex-Portfolio` — that's a DIFFERENT project!

### 2c. Pipeline Setup

3 pipelines created (TEST, ACC, PRD):

1. **Pipelines** → **New Pipeline**
2. Select **Azure Repos Git** → `DS-Master-Repo`
3. **Existing Azure Pipelines YAML file**
4. Branch: `main`, Path: `pipelines/Automation_Deploy_Databricks_{TEST|ACC|PRD}.yml`
5. **Save** (NOT Run)
6. Rename: `DS-Master-Repo-{TEST|ACC|PRD}`

### 2d. Environments

Verified these exist (Pipelines → Environments):
- `automation-test`
- `automation-acc`
- `automation-prd`

### 2e. Permissions

**Repo-level** (Project Settings → Repos → DS-Master-Repo → Security):

For **Build Service** identity (under Users, NOT Groups), set ALL to **Allow** (explicit):
- Contribute
- Contribute to pull requests
- Bypass policies when pushing
- Create branch
- Create tag
- Force push
- Read

Also applied to **Project Collection Build Service Accounts**.

> **Warning:** Inherited "Allow" is NOT sufficient. Must be explicit.

### 2f. Branch Policies

1. Project Settings → Repos → Repositories → DS-Master-Repo → Policies
2. Click `main` branch
3. Build Validation → **+**:
   - Build pipeline: ACC pipeline
   - Trigger: Automatic
   - Policy requirement: Required
   - Build expiration: Immediately when branch is updated

---

## 3. Adding a New Project

This is what you do every time a team starts a new DS project.

### 3a. Copy the Example

```bash
cp -r hello-world/ my-new-project/
```

### 3b. Edit `my-new-project/databricks.yml`

Change:
- `bundle.name` → `ds-cicd-<project-name>` (lowercase, hyphen-separated)
- `catalog` variables → your catalog prefix (e.g., `automation`, `general`, `finance`)
- `permissions` → your team's email addresses (in A and P targets)

### 3c. Edit Job YAML (`my-new-project/resources/`)

1. Rename `hello_world.job.yml` → `<your_project>.job.yml`
2. Change:
   - Job name and job key
   - Notebook paths (relative: `../src/notebooks/<name>.py`)
   - Schedule (cron expression)
   - Cluster size / VM type
   - `job_cluster_key` references
3. Keep `pause_status: PAUSED` for first deploy

### 3d. Edit `config_file.py`

Change:
- `UNITY_CATALOG` prefix to your catalog name
- Add any project-specific source table definitions

### 3e. Add Your Notebooks

Place them in `my-new-project/src/notebooks/`:
- Follow naming convention: `01_bronze_*.py`, `02_silver_*.py`, `03_gold_*.py`
- Each notebook starts with: `# MAGIC %run ./config_file`

### 3f. Deploy

Push to the repo — the existing CI/CD pipeline discovers your new bundle and deploys it:

```
feature branch → TEST (manual) → PR → ACC (automatic) → merge → PRD (automatic)
```

No new pipeline setup. No new permissions. No new repo.

---

## 4. Branch Strategy

```
main (production-ready, always deployable)
  ├── feature/task-1 → TEST (manual) → PR → ACC (automatic) → merge → PRD (automatic)
  ├── feature/task-2 → ...
  └── acc (managed by pipeline — do NOT touch manually)
```

Rules:
- No `dev` branch — use `feature/xxx` branches directly
- Never push directly to `main` — always use PRs
- Never manually push to `acc` — pipeline manages it
- Feature branches are short-lived: create → develop → test → PR → merge → delete

---

## 5. Development Workflow

```
1.  git checkout main && git pull
2.  git checkout -b feature/my-change
3.  ... edit notebooks in Databricks Git Folder ...
4.  Commit & push to feature branch
5.  Trigger TEST pipeline manually (Azure DevOps, select feature branch)
6.  Verify job in Databricks DEV workspace
7.  Open PR: feature → main
8.  ACC pipeline runs automatically (build validation)
9.  Test in ACC workspace
10. Complete PR (merge to main)
11. PRD pipeline triggers automatically
12. Verify PRD, set schedule to UNPAUSED
```

---

## 6. Local Bundle Commands

Run from inside a project folder (e.g., `hello-world/`):

```bash
# Validate bundle definition
databricks bundle validate --target D

# Deploy to development (personal workspace path)
databricks bundle deploy --target D

# Run a specific job
databricks bundle run hello_world --target D

# Deploy to test (CI-style)
databricks bundle deploy --target T
```

---

## 7. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "No bundles to deploy" | `databricks.yml` missing from project folder | Ensure it exists at `<project>/databricks.yml` |
| "File not found" in variable path | Double prefix in template path | Use `variables/...` NOT `pipelines/variables/...` |
| "Environment could not be found" | Environment not created | Create in Pipelines → Environments |
| "Non-PR build for acc" | Running ACC manually from wrong branch | Use build validation via PR |
| "GenericContribute permission" | Build Service missing permissions | Set explicit Allow (Section 2e) |
| "notebook ... not found" | Wrong path or missing extension | Use `../src/notebooks/<name>.py` relative to resources/ |
| Deploy OK but no job visible | Looking at wrong workspace | Check workspace for the correct target |

---

## Reference Tables

### Workspace Org IDs

| Workspace | Org ID | Host |
|-----------|--------|------|
| DEV/TEST | `7181820732839861` | `adb-7181820732839861.1.azuredatabricks.net` |
| ACC | `4796304964978539` | `adb-4796304964978539.19.azuredatabricks.net` |
| PRD | `4844910598668398` | `adb-4844910598668398.18.azuredatabricks.net` |

### Cluster Policy IDs

| Workspace | Policy ID | Policy Name |
|-----------|-----------|-------------|
| DEV/TEST | `306312B9730019AB` | Job Compute |
| DEV/TEST | `306312B9730019A8` | Personal Compute |
| DEV/TEST | `001FA861E645D5A1` | Automation ML Compute |
| ACC | `306312B973005677` | Job Compute |
| PRD | `306312B973005150` | Job Compute |

### Pipeline Triggers

| Pipeline | Trigger | Branch |
|----------|---------|--------|
| TEST | Manual | `feature/xxx` |
| ACC | Build validation (automatic on PR) | via PR |
| PRD | Automatic on merge to `main` | `main` |

---

## Checklist — New Project

- [ ] Copied `hello-world/` to new project folder
- [ ] `databricks.yml` customized (bundle name, catalog, permissions)
- [ ] Job YAML renamed and customized (job name, paths, schedule, cluster)
- [ ] `config_file.py` updated (catalog prefix)
- [ ] Notebooks added to `src/notebooks/`
- [ ] Feature branch pushed
- [ ] TEST pipeline ran successfully
- [ ] Job visible in Databricks, tasks completed
- [ ] PR opened → ACC pipeline passed
- [ ] Merged to main → PRD deployed
- [ ] Schedule set to UNPAUSED in PRD after verification
