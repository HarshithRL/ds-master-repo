"""
Database utilities for Air Monitoring V2 App.
Features: row_id (UUID), upload_log, safe UPDATE by row_id, user tracking.
"""
import os
import pandas as pd
import uuid
from datetime import datetime
from databricks.sdk import WorkspaceClient
from databricks import sql as databricks_sql
from databricks.sdk.core import Config
from utils.config import (
    UNITY_CATALOG, VOLUME_PATH, VOLUME_NAME, VOLUME_SUBFOLDER,
    WAREHOUSE_ID, SITES_TABLE, OUTPUT_TABLE, UPLOAD_LOG_TABLE, DEDUP_GRAIN,
    AUTH_MODE
)


# ============================================================
# Connection — supports SPN and User auth modes
# Toggle via AUTH_MODE env var in config.py / app.yaml
# ============================================================
def get_connection():
    """Get SQL connection using the configured auth mode.
    
    AUTH_MODE='spn'  → App's service principal (shared identity)
    AUTH_MODE='user' → Logged-in user's token (per-user permissions)
    """
    import streamlit as st
    cfg = Config()
    host = cfg.host.replace("https://", "").replace("http://", "")
    http_path = f"/sql/1.0/warehouses/{WAREHOUSE_ID}"

    if AUTH_MODE == "user":
        # On-behalf-of-user: use the forwarded access token from Streamlit headers
        user_token = st.context.headers.get("x-forwarded-access-token")
        if not user_token:
            raise RuntimeError(
                "User auth mode enabled but no access token found in headers. "
                "Ensure 'permission' is set in app.yaml and the app is deployed with user auth."
            )
        return databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=user_token,
        )
    else:
        # Default: App service principal (credentials auto-detected from env)
        return databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            credentials_provider=lambda: cfg.authenticate,
        )


# ============================================================
# Current User Identity
# ============================================================
def get_current_user_email() -> str:
    """Get the current user's email.
    
    In user auth mode: extracted from Streamlit headers.
    In SPN mode: falls back to Streamlit user_info (if available).
    """
    import streamlit as st
    # Streamlit on Databricks Apps always provides user info
    user_info = st.context.headers.get("x-forwarded-email", "")
    if user_info:
        return user_info.lower()
    # Fallback: experimental Streamlit user info
    try:
        return st.experimental_user.email.lower()
    except Exception:
        return "unknown"


# ============================================================
# Query
# ============================================================
def execute_query(query: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()
    finally:
        conn.close()


# ============================================================
# Sites
# ============================================================
def get_sites() -> pd.DataFrame:
    return execute_query(f"SELECT * FROM {SITES_TABLE} ORDER BY site_name")


# ============================================================
# Output Table Schema (with row_id)
# ============================================================
OUTPUT_COLUMNS = [
    "row_id",  # UUID — unique per row, enables safe UPDATE
    "Site_name", "Code", "Site_Address", "upload_date", "Document_name",
    "Report_number", "Sample_no", "Pump_Location", "Lab_name",
    "Project_Name", "Building", "Sample_Date", "Analysis_method",
    "Followed_Norm", "Volume", "Concentration_result", "Concentration_unit",
    "Concentration_result_in_f_ml", "Frozen_Docs", "PDF_URL",
    "Flag_EM_Concentration", "Flag_High_Concentration",
    "Delete_docs", "row_status", "removal_reason", "status_updated_at",
    "uploaded_by", "upload_batch_id", "modified_by"
]


def _ensure_output_table():
    """Create output table if not exists, and add row_id column if missing."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cols_def = []
            for col in OUTPUT_COLUMNS:
                if col in ("upload_date", "status_updated_at"):
                    cols_def.append(f"`{col}` TIMESTAMP")
                elif col == "Flag_EM_Concentration":
                    cols_def.append(f"`{col}` DOUBLE")
                elif col == "Flag_High_Concentration":
                    cols_def.append(f"`{col}` BOOLEAN")
                else:
                    cols_def.append(f"`{col}` STRING")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {OUTPUT_TABLE} ({', '.join(cols_def)})")
            # Add row_id if table existed without it
            try:
                cursor.execute(f"ALTER TABLE {OUTPUT_TABLE} ADD COLUMN `row_id` STRING FIRST")
            except Exception:
                pass  # column already exists
    finally:
        conn.close()


def _ensure_upload_log_table():
    """Create upload_log table if not exists."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {UPLOAD_LOG_TABLE} (
                    upload_id STRING,
                    batch_id STRING,
                    filename STRING,
                    site_code STRING,
                    site_name STRING,
                    uploaded_by STRING,
                    upload_time TIMESTAMP,
                    num_records INT,
                    num_duplicates_found INT,
                    num_saved INT,
                    status STRING,
                    volume_path STRING
                )
            """)
    finally:
        conn.close()


# ============================================================
# Write (INSERT with row_id)
# ============================================================
def write_to_output_table(df: pd.DataFrame, uploaded_by: str = "unknown", batch_id: str = ""):
    """Insert rows with auto-generated row_id UUID."""
    _ensure_output_table()
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # Add row_id and metadata
            if "row_id" not in df.columns:
                df["row_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
            if "uploaded_by" not in df.columns:
                df["uploaded_by"] = uploaded_by
            if "upload_batch_id" not in df.columns:
                df["upload_batch_id"] = batch_id

            # Align columns
            for col in OUTPUT_COLUMNS:
                if col not in df.columns:
                    df[col] = None
            df_aligned = df[OUTPUT_COLUMNS].copy()

            # Batch insert
            batch_size = 50
            for start in range(0, len(df_aligned), batch_size):
                batch = df_aligned.iloc[start:start + batch_size]
                rows = []
                for _, row in batch.iterrows():
                    values = []
                    for col, val in zip(OUTPUT_COLUMNS, row):
                        if pd.isna(val) or val is None:
                            values.append("NULL")
                        elif col == "Flag_EM_Concentration":
                            try: values.append(str(float(val)))
                            except: values.append("NULL")
                        elif col == "Flag_High_Concentration":
                            values.append(str(bool(val)).upper())
                        else:
                            values.append(f"\'{str(val).replace(chr(39), chr(39)+chr(39))}\'" )
                    rows.append(f"({', '.join(values)})")

                columns = ", ".join([f"`{c}`" for c in OUTPUT_COLUMNS])
                cursor.execute(f"INSERT INTO {OUTPUT_TABLE} ({columns}) VALUES {', '.join(rows)}")
    finally:
        conn.close()


# ============================================================
# Update (by row_id — BATCHED MERGE for performance)
# ============================================================
def update_rows(df: pd.DataFrame, modified_by: str = "unknown"):
    """Update rows by row_id using batched MERGE for performance and conflict resilience."""
    import time
    if "row_id" not in df.columns:
        raise ValueError("Cannot update without row_id column.")
    
    # Track who made the modification
    df = df.copy()
    df["modified_by"] = modified_by
    df["status_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Columns to update (exclude row_id)
    update_cols = [c for c in df.columns if c != "row_id"]
    
    def _escape_val(val, col):
        """Format a value for SQL."""
        if pd.isna(val) or val is None:
            return "NULL"
        if col == "Flag_EM_Concentration":
            try: return str(float(val))
            except: return "NULL"
        if col == "Flag_High_Concentration":
            return str(bool(val)).upper()
        return "'" + str(val).replace("'", "''") + "'"
    
    def _build_merge_batch(batch_df):
        """Build a single MERGE statement for a batch of rows."""
        value_rows = []
        for _, row in batch_df.iterrows():
            row_id_escaped = str(row["row_id"]).replace("'", "''")
            vals = [f"'{row_id_escaped}'"]
            for col in update_cols:
                vals.append(_escape_val(row[col], col))
            value_rows.append(f"({', '.join(vals)})")
        
        col_aliases = ["row_id"] + update_cols
        col_defs = ", ".join([f"`{c}`" for c in col_aliases])
        values_sql = ",\n".join(value_rows)
        
        set_clause = ", ".join([f"t.`{c}` = s.`{c}`" for c in update_cols])
        
        merge_sql = (
            f"MERGE INTO {OUTPUT_TABLE} AS t\n"
            f"USING (SELECT * FROM (VALUES\n{values_sql}\n) AS vals({col_defs})) AS s\n"
            f"ON t.row_id = s.row_id\n"
            f"WHEN MATCHED THEN UPDATE SET {set_clause}"
        )
        return merge_sql
    
    # Process in batches of 200 rows
    BATCH_SIZE = 200
    MAX_RETRIES = 3
    total_rows = len(df)
    
    for batch_start in range(0, total_rows, BATCH_SIZE):
        batch_df = df.iloc[batch_start:batch_start + BATCH_SIZE]
        merge_sql = _build_merge_batch(batch_df)
        
        for attempt in range(1, MAX_RETRIES + 1):
            conn = get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(merge_sql)
                break  # Success
            except Exception as e:
                if "DELTA_CONCURRENT" in str(e) and attempt < MAX_RETRIES:
                    time.sleep(2 * attempt)  # Backoff: 2s, 4s
                    continue
                raise e
            finally:
                conn.close()


# ============================================================
# Duplicate Check
# ============================================================
def check_duplicates(new_df: pd.DataFrame, site_code: str) -> dict:
    """
    Check new records against existing DB on DEDUP_GRAIN.
    Returns {row_index: {existing_doc, existing_date, existing_values}}.
    """
    try:
        cols = ", ".join([f"`{c}`" for c in DEDUP_GRAIN])
        existing = execute_query(
            f"SELECT {cols}, Document_name, upload_date, row_id "
            f"FROM {OUTPUT_TABLE} "
            f"WHERE Code = \'{site_code}\' AND row_status IN (\'active\', \'modified\')"
        )
        if existing.empty:
            return {}

        duplicates = {}
        for idx, row in new_df.iterrows():
            mask = pd.Series([True] * len(existing))
            for col in DEDUP_GRAIN:
                val = str(row.get(col, "")).strip().lower()
                if val and val not in ("none", "nan", "not specified", ""):
                    mask = mask & (existing[col].astype(str).str.strip().str.lower() == val)
            
            matches = existing[mask]
            if not matches.empty:
                m = matches.iloc[0]
                duplicates[idx] = {
                    "existing_doc": m.get("Document_name", "?"),
                    "existing_date": str(m.get("upload_date", ""))[:10],
                    "existing_row_id": m.get("row_id", ""),
                }
        return duplicates
    except Exception:
        return {}


# ============================================================
# Upload Log
# ============================================================
def log_upload(filename: str, site_code: str, site_name: str, uploaded_by: str,
              num_records: int, num_duplicates: int, num_saved: int, 
              batch_id: str, volume_path: str, status: str = "success"):
    """Log an upload event for history tracking."""
    _ensure_upload_log_table()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            upload_id = str(uuid.uuid4())
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(f"""
                INSERT INTO {UPLOAD_LOG_TABLE} 
                (upload_id, batch_id, filename, site_code, site_name, uploaded_by, 
                 upload_time, num_records, num_duplicates_found, num_saved, status, volume_path)
                VALUES (
                    \'{upload_id}\', \'{batch_id}\', \'{filename.replace(chr(39),"")}\'  ,
                    \'{site_code}\', \'{site_name.replace(chr(39),"")}\'  , \'{uploaded_by}\',
                    \'{now}\', {num_records}, {num_duplicates}, {num_saved},
                    \'{status}\', \'{volume_path.replace(chr(39),"")}\' 
                )
            """)
    finally:
        conn.close()


def get_upload_history(limit: int = 100) -> pd.DataFrame:
    """Get recent upload history."""
    try:
        return execute_query(
            f"SELECT * FROM {UPLOAD_LOG_TABLE} ORDER BY upload_time DESC LIMIT {limit}"
        )
    except:
        return pd.DataFrame()


# ============================================================
# Volume Operations
# ============================================================
def upload_file_to_volume(uploaded_file, site_code: str = "") -> str:
    # Use user authentication for volume operations.
    # Clear SPN env vars so WorkspaceClient uses the user's token instead.
    import streamlit as st
    user_token = st.context.headers.get("x-forwarded-access-token")
    _saved_cid = os.environ.pop("DATABRICKS_CLIENT_ID", None)
    _saved_csec = os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
    try:
        w = WorkspaceClient(
            host=os.environ.get("DATABRICKS_HOST"),
            token=user_token
        )
    except Exception:
        # Fallback: use default SDK auth
        w = WorkspaceClient()
    finally:
        if _saved_cid:
            os.environ["DATABRICKS_CLIENT_ID"] = _saved_cid
        if _saved_csec:
            os.environ["DATABRICKS_CLIENT_SECRET"] = _saved_csec
    target_path = VOLUME_PATH  # /Volumes/{catalog}/{bronze_schema}/{volume_name}/air_monitoring/uploaded_reports
    if site_code:
        target_path = f"{target_path}/{site_code}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uploaded_file.name}"
    full_path = f"{target_path}/{filename}"
    w.files.upload(full_path, uploaded_file.getvalue(), overwrite=True)
    return full_path
