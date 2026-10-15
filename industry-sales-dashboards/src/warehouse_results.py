import re
from json import dumps
from pathlib import Path
from time import monotonic, sleep


CANCELLATION_DATASET = "ds_cancellations_detail_7d"
REMOTE_ORDER_TABLE = "dbx_fact_o2c_-_self_service_-_sales_orders"


def is_cancellation_plan(plan):
    return (plan["dashboard"], plan["dataset"]) == ("open_orders", CANCELLATION_DATASET)


def prioritize_cancellation(plans):
    return sorted(plans, key=lambda plan: not is_cancellation_plan(plan))


def execute_warehouse_statement(workspace, warehouse_id, statement, timeout_seconds=600):
    if not re.fullmatch(r"[a-f0-9]{16}", warehouse_id):
        raise ValueError("Invalid SQL warehouse ID")
    deadline = monotonic() + timeout_seconds
    response = workspace.statement_execution.execute_statement(warehouse_id=warehouse_id, statement=statement, wait_timeout="50s")
    statement_id = response.statement_id
    print(dumps({"stage": "warehouse_statement_submitted", "statement_id": statement_id, "state": response.status.state.value}), flush=True)
    try:
        while response.status.state.value in ("PENDING", "RUNNING"):
            if monotonic() >= deadline:
                raise TimeoutError(f"Warehouse statement {statement_id} exceeded {timeout_seconds}s")
            sleep(min(2, max(0, deadline - monotonic())))
            response = workspace.statement_execution.get_statement(statement_id)
        if response.status.state.value != "SUCCEEDED":
            error = response.status.error
            message = error.message if error else response.status.state.value
            raise RuntimeError(f"Warehouse statement {statement_id} failed: {message}")
        if response.manifest and response.manifest.truncated:
            raise ValueError(f"Warehouse statement {statement_id} returned truncated metadata")
        print(dumps({"stage": "warehouse_statement_verified", "statement_id": statement_id}), flush=True)
        return response
    except BaseException:
        if response.status.state.value in ("PENDING", "RUNNING"):
            try:
                workspace.statement_execution.cancel_execution(statement_id)
            except Exception as cancel_error:
                print(dumps({"stage": "warehouse_cancel_unconfirmed", "statement_id": statement_id, "error_type": type(cancel_error).__name__}), flush=True)
        raise


def validate_quoted_order_scan(plan):
    queries = [line.split("External engine query:", 1)[1].strip() for line in plan.splitlines() if "External engine query:" in line]
    order_queries = [query for query in queries if REMOTE_ORDER_TABLE.casefold() in query.casefold()]
    pattern = r'\bFROM\s+(?:"PBI"\."' + re.escape(REMOTE_ORDER_TABLE) + r'"|\[PBI\]\.\[' + re.escape(REMOTE_ORDER_TABLE) + r'\])(?:\s|$)'
    if not order_queries or any(not re.search(pattern, query, flags=re.IGNORECASE) for query in order_queries):
        raise ValueError("Warehouse plan must quote the hyphenated O2C remote table; refusing the broken job-compute JDBC path")


def preflight_cancellation_warehouse(workspace, warehouse_id, source_statement, expected_identity, expected_workspace_id):
    host = workspace.config.host.rstrip("/")
    if not re.fullmatch(r"https://adb-" + re.escape(str(expected_workspace_id)) + r"\.[0-9]+\.azuredatabricks\.net", host):
        raise ValueError("SQL warehouse client does not match the validated job workspace")
    identity = execute_warehouse_statement(workspace, warehouse_id, "SELECT current_user() AS job_identity", timeout_seconds=60)
    rows = identity.result.data_array if identity.result else []
    if len(rows) != 1 or len(rows[0]) != 1 or not isinstance(rows[0][0], str) or rows[0][0].casefold() != expected_identity.casefold():
        raise ValueError(f"SQL warehouse identity {rows!r} differs from the Spark job identity {expected_identity!r}")
    response = execute_warehouse_statement(workspace, warehouse_id, "EXPLAIN FORMATTED " + source_statement, timeout_seconds=120)
    if not response.result or response.result.next_chunk_index is not None:
        raise ValueError("Complete warehouse query-plan metadata is required")
    plan = "\n".join(str(value) for row in response.result.data_array or [] for value in row)
    validate_quoted_order_scan(plan)


def warehouse_stage_sql(statement, path):
    match = re.fullmatch(r"/Volumes/(automation_[dap])/bronze/bronze_volume/SC_BI_industry_sales_result_scratch/([DTAP])/[a-f0-9]{32}/open_orders/ds_cancellations_detail_7d/[0-9]+", str(path))
    if not match or match.group(1) != {"D": "automation_d", "T": "automation_d", "A": "automation_a", "P": "automation_p"}[match.group(2)]:
        raise ValueError("Warehouse staging is restricted to this batch's cancellation output")
    return f"INSERT OVERWRITE DIRECTORY '{path}' USING PARQUET\n" + statement


def stage_cancellation_warehouse(spark, workspace, warehouse_id, statement, path, timeout_seconds=600):
    command = warehouse_stage_sql(statement, path)
    schema = spark.sql(statement).schema
    Path(path).mkdir(parents=True, exist_ok=False)
    execute_warehouse_statement(workspace, warehouse_id, command, timeout_seconds=timeout_seconds)
    observed = spark.read.parquet(str(path)).schema
    if [(field.name, field.dataType) for field in schema.fields] != [(field.name, field.dataType) for field in observed.fields]:
        raise ValueError("Warehouse cancellation staging changed native column names or types")
    return spark.read.schema(schema).parquet(str(path))