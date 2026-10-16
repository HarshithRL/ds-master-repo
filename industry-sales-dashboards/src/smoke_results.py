from allocation_stages import freeze_sql_date, query_parts
from dataset_results import local_result, parameter_defaults, table_edits, unique_result_producers
from durable_results import cleanup_result_scratch, result_dataset_scratch, stage_result_frame
from industry_config import MAPPING_COLUMNS, validate_mapping
from source_snapshots import collect_source_columns, quote_column
from warehouse_results import CANCELLATION_DATASET, REMOTE_ORDER_TABLE, preflight_cancellation_warehouse, stage_cancellation_warehouse
from sqlglot import exp, parse_one


def source_probe_sql(source, source_catalog):
    if not source["columns"]:
        raise ValueError("Smoke probes require an explicit column projection")
    columns = ", ".join(quote_column(name) for name in source["columns"])
    relation = ".".join(quote_column(name) for name in (source_catalog, "pbi", source["source_table"]))
    predicate = ""
    if source["source_table"] == REMOTE_ORDER_TABLE:
        predicate = " WHERE `Document Type` IN ('YOR','YSO','YKE','YKB') AND `Rejection Status`='C' AND `FK Sales Organization` IS NOT NULL"
    return f"SELECT {columns} FROM {relation}{predicate} LIMIT 1"


def check_dataset_contract(spark, plan, replacements, business_date):
    temporary = []

    def prepare(statement):
        return freeze_sql_date(parameter_defaults(table_edits(statement, replacements)), business_date)

    def bounded_schema(statement):
        if any(table.catalog or table.db for table in parse_one(statement, read="databricks").find_all(exp.Table)):
            raise ValueError("Smoke schema analysis retained a non-fixture table reference")
        return spark.sql(statement).schema

    try:
        expected = bounded_schema(prepare(plan["source_sql"]))
        consumer = prepare(plan["consumer_sql"])
        for producer in plan["producers"]:
            stages, final = query_parts(prepare(producer["sql"]))
            for name, statement in stages:
                schema = bounded_schema(statement)
                spark.createDataFrame([], schema).createOrReplaceTempView(name)
                temporary.append(name)
            schema = bounded_schema(final)
            spark.createDataFrame([], schema).createOrReplaceTempView(producer["component"])
            temporary.append(producer["component"])
            if producer["table"]:
                name = "SC_BI_smoke_result_" + str(len(temporary))
                spark.createDataFrame([], schema).createOrReplaceTempView(name)
                temporary.append(name)
                consumer = consumer.replace(local_result(producer["table"]), quote_column(name))
        actual = bounded_schema(consumer)
        if [(field.name, field.dataType) for field in expected.fields] != [(field.name, field.dataType) for field in actual.fields]:
            raise ValueError(f"Dataset output contract changed: {plan['dashboard']}:{plan['dataset']}")
    finally:
        for name in set(temporary):
            spark.catalog.dropTempView(name)


def run_smoke_checks(spark, workspace, warehouse_id, plans, source_schemas, mapping_rows, source_catalog, scratch, workspace_id, log):
    identities = {(plan["dashboard"], plan["dataset"]) for plan in plans}
    if len(plans) != 18 or len(identities) != 18:
        raise ValueError("Smoke checks require all 18 unique active datasets")
    unique_result_producers(plans)
    context = spark.sql("SELECT current_user() AS job_identity, CURRENT_DATE() AS business_date").first()
    sources = collect_source_columns([plan["source_sql"] for plan in plans], source_schemas)
    for source in sources:
        if source["columns"] is None:
            source["columns"] = source_schemas[source["source_table"]]
    sources.sort(key=lambda source: source["source_table"] != REMOTE_ORDER_TABLE)
    order_source = next(source for source in sources if source["source_table"] == REMOTE_ORDER_TABLE)
    log("smoke_warehouse_started")
    preflight_cancellation_warehouse(workspace, warehouse_id, source_probe_sql(order_source, source_catalog), context["job_identity"], workspace_id)
    replacements = {}
    temporary = []
    succeeded = False
    try:
        for index, source in enumerate(sources):
            query = source_probe_sql(source, source_catalog)
            log("smoke_source_started", source=source["source_table"], columns=len(source["columns"]), row_limit=1)
            if source["source_table"] == REMOTE_ORDER_TABLE:
                path = result_dataset_scratch(scratch, "open_orders", CANCELLATION_DATASET) / "0"
                sample = stage_cancellation_warehouse(spark, workspace, warehouse_id, query, path, timeout_seconds=120)
            else:
                frame = spark.sql(query)
                sample = stage_result_frame(spark, frame, scratch / ("source_" + str(index)))
            rows = sample.limit(2).collect()
            if len(rows) > 1:
                raise ValueError("Source smoke probe exceeded its one-row boundary")
            name = "SC_BI_smoke_source_" + str(index)
            spark.createDataFrame([], sample.schema).createOrReplaceTempView(name)
            temporary.append(name)
            for catalog in ("synapse-prd", source_catalog, "${var.source_catalog}"):
                replacements[catalog + ".pbi." + source["source_table"]] = quote_column(name)
            log("smoke_source_verified", source=source["source_table"], rows=len(rows))
        rows = validate_mapping(mapping_rows)
        schema = ", ".join(column + " STRING" for column in MAPPING_COLUMNS)
        spark.createDataFrame(rows, schema).createOrReplaceTempView("SC_BI_smoke_mapping")
        temporary.append("SC_BI_smoke_mapping")
        for identity in ("supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping", "${var.catalog}.gold.${var.mapping_table_name}"):
            replacements[identity] = "SC_BI_smoke_mapping"
        for plan in plans:
            log("smoke_dataset_started", dashboard=plan["dashboard"], dataset=plan["dataset"], check="schema_only_on_bounded_sources")
            check_dataset_contract(spark, plan, replacements, context["business_date"])
            log("smoke_dataset_verified", dashboard=plan["dashboard"], dataset=plan["dataset"])
        succeeded = True
        log("smoke_checks_passed", sources=len(sources), datasets=len(plans), source_row_limit=1)
    finally:
        for name in set(temporary):
            spark.catalog.dropTempView(name)
        if succeeded:
            try:
                cleanup_result_scratch(scratch)
            except Exception as error:
                log("smoke_cleanup_failed", path=str(scratch), error_type=type(error).__name__)