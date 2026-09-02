# App Source Code

This folder contains the app source code that gets deployed to each environment.

Copy the contents of `/Workspace/Users/mustafaarda.bicakci@etexgroup.com/Air-Monitoring-V2-App/` here:

- `app.py` — Streamlit main app
- `app.yaml` — NOT here (env-specific versions in `/config/`)
- `requirements.txt` — Python dependencies
- `etex_logo.jpeg` — Logo asset
- `utils/` — Python modules
  - `__init__.py`
  - `config.py` — Env-aware config (reads from env vars)
  - `db_utils.py` — SQL Warehouse connection + CRUD
  - `doc_intelligence.py` — Azure Document Intelligence
  - `llm_processor.py` — GPT extraction + normalization

## Important

- `config.py` must use `os.environ.get()` for all environment-specific values
- `app.yaml` is NOT in this folder — the deploy script copies the correct one from `config/`
- Never hardcode warehouse IDs, catalog names, or secrets
