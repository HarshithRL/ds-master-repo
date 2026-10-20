import json
import re
from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from ursa_config import BUNDLE_NAME, ENVIRONMENTS, quote_column, relation, validate_environment
from ursa_plan import collect_source_columns, consumer_query, freeze_business_date, input_view, localize_sources, preview_consumer_query


MARKER = "__ursa_kpi_snapshot_id"
OWNER_PROPERTY = "ursa_kpi.bundle"
DATASETS = {
    "ursa_kpi_data", "test_invoiced_value", "hypercare_mock", "hc_baseline",
    "hc_actuals_vs_baseline", "hc_matrix_formatted", "o2c_live_matrix",
}


def log(stage, **details):
    print(json.dumps({"stage": stage, "at": datetime.now(timezone.utc).isoformat(), **details}), flush=True)


def load_plan(config_path):
    plan = json.loads((Path(config_path) / "dashboard_plan.json").read_text())
    datasets = plan.get("datasets", [])
    if plan.get("format_version") != 1 or len(datasets) != len(DATASETS) or {dataset["dataset"] for dataset in datasets} != DATASETS:
        raise ValueError("The complete seven-dataset release plan is required")
    if plan.get("source_inventory") != {"datasets": 7, "pages": 14, "widgets": 50}:
        raise ValueError("The original dashboard inventory changed without an explicit release")
    if not re.fullmatch(r"[0-9a-f]{64}", plan.get("source_sha256", "")):
        raise ValueError("Missing source provenance")
    if collect_source_columns([dataset["source_sql"] for dataset in datasets]) != plan.get("sources"):
        raise ValueError("Source projection does not match the actual calculations")
    for dataset in datasets:
        if dataset["component"] != "result_" + dataset["dataset"] or dataset["local_sql"] != localize_sources(dataset["source_sql"]):
            raise ValueError("Dataset producer identity or source rewrite changed")
        if dataset["consumer_sql"] != consumer_query(dataset["source_sql"], dataset["component"]):
            raise ValueError("Consumer SQL does not match its dataset result contract")
    return plan


def source_projection(source):
    identity = source["identity"].split(".")
    if len(identity) != 3 or identity[:2] != ["synapse-prd", "pbi"]:
        raise ValueError("Undeclared source catalog or schema")
    projection = ", ".join(quote_column(column) for column in source["columns"])
    if not projection:
        raise ValueError("A bounded source projection is required")
    return "SELECT " + projection + " FROM " + ".".join(quote_column(part) for part in identity)


def scratch_root(catalog, target, batch):
    if target not in ENVIRONMENTS or catalog != ENVIRONMENTS[target][0] or not re.fullmatch(r"[0-9a-f]{32}", batch):
        raise ValueError("Scratch target, catalog and batch must agree")
    return Path(f"/Volumes/{catalog}/bronze/bronze_volume/URSA_KPI/{target}/{batch}")


def cleanup_scratch(path, catalog, target, batch):
    root = scratch_root(catalog, target, batch)
    if Path(path) != root:
        raise ValueError("Refusing cleanup outside this bundle's isolated batch directory")
    if Path(path).is_symlink():
        raise ValueError("Refusing scratch symlink cleanup")
    if Path(path).exists():
        rmtree(path)


def validate_columns(columns):
    if not columns or len({column.casefold() for column in columns}) != len(columns) or MARKER.casefold() in {column.casefold() for column in columns}:
        raise ValueError("Result columns must be nonempty, unique and outside the reserved namespace")
    for column in columns:
        quote_column(column)


def validate_schema(required, stored):
    if required != stored:
        raise ValueError("Native result schema changed; explicit migration is required")


def schema_fields(frame):
    return [(field.name, field.dataType) for field in frame.schema.fields]


def stage_frame(spark, frame, path):
    schema = frame.schema
    frame.write.mode("error").parquet(str(path))
    stored = spark.read.schema(schema).parquet(str(path))
    validate_schema(schema_fields(frame), schema_fields(stored))
    return stored


def view_query(raw, state, columns):
    validate_columns(columns)
    projection = ", ".join(quote_column(column) for column in columns)
    return f"SELECT {projection} FROM {raw} WHERE `{MARKER}` = (SELECT snapshot_id FROM {state})"


def view_ddl(view, query, exists):
    if exists:
        return f"ALTER VIEW {view} AS {query}"
    return f"CREATE VIEW {view} TBLPROPERTIES ('{OWNER_PROPERTY}'='{BUNDLE_NAME}') AS {query}"


def validate_receipts(plan, receipts):
    expected = {dataset["dataset"] for dataset in plan["datasets"]}
    actual = [receipt.get("dataset") for receipt in receipts]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Every unique dataset must verify before the publication pointer changes")
    for receipt in receipts:
        if receipt.get("verified") is not True or type(receipt.get("rows")) is not int or receipt["rows"] < 0:
            raise ValueError("A native write/read receipt is required for every dataset")
        if receipt["dataset"] != "test_invoiced_value" and receipt["rows"] == 0:
            raise ValueError("A source dataset with a known nonempty spine cannot publish an empty result")
        validate_columns(receipt.get("columns", []))


def validate_consumer_schema(spark, dataset, frame):
    frame.createOrReplaceTempView("URSA_KPI_preview_result")
    consumer = spark.sql(preview_consumer_query(dataset["consumer_sql"]))
    if consumer.columns != frame.columns:
        raise ValueError(f"Consumer schema differs from its computed result: {dataset['dataset']}")
    consumer.limit(0).collect()
    log("consumer_schema_verified_before_publication", dataset=dataset["dataset"])


def check_owned(spark, name, expected_type):
    if not spark.catalog.tableExists(name):
        return
    actual_type = spark.catalog.getTable(name).tableType
    if (actual_type == "VIEW") != (expected_type == "VIEW"):
        raise ValueError(f"Existing object has the wrong relation type: {name}")
    properties = {row["key"]: row["value"] for row in spark.sql(f"SHOW TBLPROPERTIES {name}").collect()}
    if properties.get(OWNER_PROPERTY) != BUNDLE_NAME:
        raise ValueError(f"Refusing to modify an object not owned by this bundle: {name}")


def register_sources(spark, plan):
    for source in plan["sources"]:
        projected = spark.sql(source_projection(source))
        if projected.columns != source["columns"]:
            raise ValueError(f"Native source projection changed: {source['identity']}")
        projected.createOrReplaceTempView(input_view(source["identity"]))
        log("source_projection_ready", source=source["identity"], columns=len(source["columns"]))


def initialize_state(spark, state, audit):
    properties = f"TBLPROPERTIES ('{OWNER_PROPERTY}'='{BUNDLE_NAME}')"
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {state} USING DELTA {properties} AS "
        "SELECT CAST(NULL AS STRING) AS snapshot_id, CAST(NULL AS DATE) AS snapshot_as_of_date, "
        "CAST(NULL AS TIMESTAMP) AS snapshot_completed_at, CAST(NULL AS STRING) AS source_sha256, "
        "CAST(NULL AS STRING) AS result_receipts WHERE FALSE"
    ).collect()
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {audit} USING DELTA {properties} AS "
        "SELECT CAST(NULL AS STRING) AS snapshot_id, CAST(NULL AS STRING) AS status, "
        "CAST(NULL AS TIMESTAMP) AS recorded_at, CAST(NULL AS DATE) AS business_date, "
        "CAST(NULL AS STRING) AS source_sha256, CAST(NULL AS STRING) AS details_json WHERE FALSE"
    ).collect()


def append_audit(spark, audit, batch, status, business_date, source_sha256, details):
    rows = [(batch, status, datetime.now(timezone.utc), business_date, source_sha256, json.dumps(details))]
    spark.createDataFrame(
        rows, "snapshot_id STRING,status STRING,recorded_at TIMESTAMP,business_date DATE,source_sha256 STRING,details_json STRING",
    ).write.format("delta").mode("append").saveAsTable(audit)


def publish_state(spark, plan, state, batch, business_date, receipts):
    validate_receipts(plan, receipts)
    rows = [(batch, business_date, datetime.now(timezone.utc), plan["source_sha256"], json.dumps(receipts))]
    completed = spark.createDataFrame(
        rows, "snapshot_id STRING,snapshot_as_of_date DATE,snapshot_completed_at TIMESTAMP,source_sha256 STRING,result_receipts STRING",
    )
    completed.createOrReplaceTempView("URSA_KPI_completed_batch")
    spark.sql(f"INSERT OVERWRITE TABLE {state} SELECT snapshot_id,snapshot_as_of_date,snapshot_completed_at,source_sha256,result_receipts FROM URSA_KPI_completed_batch").collect()


def verify_results(spark, plan, catalog, target):
    state = relation(catalog, "gold", "result_state", target)
    completed = spark.table(state).collect()
    if len(completed) != 1 or completed[0]["source_sha256"] != plan["source_sha256"]:
        raise ValueError("There is no unique completed batch for this source release")
    receipts = json.loads(completed[0]["result_receipts"])
    validate_receipts(plan, receipts)
    expected = {receipt["dataset"]: receipt for receipt in receipts}
    for dataset in plan["datasets"]:
        statement = dataset["consumer_sql"].replace("${var.catalog}", catalog).replace("${var.result_suffix}", "_dev" if target == "D" else "")
        frame = spark.sql(statement)
        receipt = expected[dataset["dataset"]]
        if frame.columns != receipt["columns"] or frame.count() != receipt["rows"]:
            raise ValueError(f"Published dashboard result differs from its native receipt: {dataset['dataset']}")
        frame.limit(1).collect()
        log("dashboard_result_verified", dataset=dataset["dataset"], rows=receipt["rows"])
    return receipts


def execute(spark, config_path, catalog, source_catalog, target, mode):
    workspace_id = spark.conf.get("spark.databricks.clusterUsageTags.orgId")
    validate_environment(target, catalog, source_catalog, workspace_id)
    if mode not in ("preflight", "materialize", "verify"):
        raise ValueError("Unknown job execution mode")
    plan = load_plan(config_path)
    for layer in ("bronze", "silver", "gold"):
        spark.sql(f"DESCRIBE SCHEMA `{catalog}`.`{layer}`").collect()
    if mode == "verify":
        return verify_results(spark, plan, catalog, target)
    register_sources(spark, plan)
    business_date = spark.sql("SELECT CURRENT_DATE() AS business_date").first()["business_date"]
    batch = uuid4().hex
    scratch = scratch_root(catalog, target, batch)
    scratch.mkdir(parents=True, exist_ok=False)
    probe = stage_frame(spark, spark.sql("SELECT CAST(1 AS INT) AS ready"), scratch / "preflight")
    if probe.first()["ready"] != 1:
        raise ValueError("Durable staging write/read preflight failed")
    if mode == "preflight":
        for dataset in plan["datasets"]:
            frame = spark.sql(freeze_business_date(dataset["local_sql"], business_date))
            validate_columns(frame.columns)
            frame.limit(0).collect()
            log("dataset_schema_verified", dataset=dataset["dataset"], columns=frame.columns)
        cleanup_scratch(scratch, catalog, target, batch)
        log("preflight_verified", source_relations=len(plan["sources"]), datasets=len(plan["datasets"]))
        return []
    state = relation(catalog, "gold", "result_state", target)
    audit = relation(catalog, "bronze", "refresh_audit", target)
    check_owned(spark, state, "TABLE")
    check_owned(spark, audit, "TABLE")
    for dataset in plan["datasets"]:
        check_owned(spark, relation(catalog, "silver", dataset["component"], target), "TABLE")
        check_owned(spark, relation(catalog, "gold", dataset["component"], target), "VIEW")
    initialize_state(spark, state, audit)
    previous = spark.table(state).collect()
    if len(previous) > 1:
        raise ValueError("Multiple active publication batches are forbidden")
    previous_batch = previous[0]["snapshot_id"] if previous else None
    if previous_batch is not None and not re.fullmatch(r"[0-9a-f]{32}", previous_batch):
        raise ValueError("Invalid previous publication identity")
    append_audit(spark, audit, batch, "started", business_date, plan["source_sha256"], {"sources": plan["sources"]})
    receipts = []
    try:
        from pyspark.sql import functions as sql_functions

        for dataset in plan["datasets"]:
            log("dataset_started", dataset=dataset["dataset"], snapshot_id=batch)
            computed = spark.sql(freeze_business_date(dataset["local_sql"], business_date))
            validate_columns(computed.columns)
            frame = stage_frame(spark, computed, scratch / dataset["dataset"])
            row_count = frame.count()
            raw = relation(catalog, "silver", dataset["component"], target)
            view = relation(catalog, "gold", dataset["component"], target)
            captured = frame.withColumn(MARKER, sql_functions.lit(batch))
            if not spark.catalog.tableExists(raw):
                captured.limit(0).createOrReplaceTempView("URSA_KPI_result_schema")
                spark.sql(
                    f"CREATE TABLE {raw} USING DELTA TBLPROPERTIES "
                    f"('{OWNER_PROPERTY}'='{BUNDLE_NAME}','delta.columnMapping.mode'='name') "
                    "AS SELECT * FROM URSA_KPI_result_schema"
                ).collect()
            validate_schema(schema_fields(captured), schema_fields(spark.table(raw)))
            captured.write.format("delta").mode("append").saveAsTable(raw)
            actual = spark.table(raw).where(sql_functions.col(MARKER) == batch).select(*[sql_functions.col(quote_column(column)) for column in frame.columns])
            if frame.exceptAll(actual).limit(1).count() or actual.exceptAll(frame).limit(1).count():
                raise ValueError(f"Native result write/read multiset equality failed: {dataset['dataset']}")
            validate_consumer_schema(spark, dataset, frame)
            spark.sql(view_ddl(view, view_query(raw, state, frame.columns), spark.catalog.tableExists(view))).collect()
            receipt = {"dataset": dataset["dataset"], "rows": row_count, "columns": frame.columns, "verified": True}
            receipts.append(receipt)
            log("dataset_write_read_verified", **receipt)
        publish_state(spark, plan, state, batch, business_date, receipts)
    except Exception as error:
        try:
            append_audit(spark, audit, batch, "failed", business_date, plan["source_sha256"], {"error_type": type(error).__name__, "error": str(error)})
        except Exception as audit_error:
            log("failure_audit_unavailable", error=str(audit_error))
        raise
    log("published", snapshot_id=batch, business_date=business_date.isoformat(), datasets=len(receipts))
    try:
        append_audit(spark, audit, batch, "published", business_date, plan["source_sha256"], {"receipts": receipts})
        retained = [batch] + ([previous_batch] if previous_batch else [])
        keep = ",".join("'" + value + "'" for value in retained)
        for dataset in plan["datasets"]:
            raw = relation(catalog, "silver", dataset["component"], target)
            spark.sql(f"DELETE FROM {raw} WHERE `{MARKER}` NOT IN ({keep})").collect()
        cleanup_scratch(scratch, catalog, target, batch)
    except Exception as error:
        log("post_publication_cleanup_warning", snapshot_id=batch, error_type=type(error).__name__, error=str(error))
    return receipts