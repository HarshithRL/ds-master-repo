import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

def migration_root() -> Path:
    if "--migration-root" in sys.argv:
        return Path(sys.argv[sys.argv.index("--migration-root") + 1]).resolve()
    script = globals().get("__file__")
    if script:
        return Path(script).resolve().parent
    raise ValueError("The Databricks task must provide --migration-root")


ROOT = migration_root()
sys.path.insert(0, str(ROOT))
from transfer import (
    Column, FORMAT, TABLES, load_contract, load_snapshot, package_zip, pristine_bootstrap_id,
    snapshot_name, target_column_name, validate_columns, validate_records, volume_path, write_csv,
)


WORKSPACES = {"automation_d": "7181820732839861", "automation_a": "4796304964978539", "automation_p": "4844910598668398"}
SOURCE = "engineering_global_pmo_s.pmo"
CONTRACT_PATH = ROOT / "table_contract.json"
NULLABLE_UPGRADES = {("users", "permissions"), ("projects", "wbs_codes"), ("projects", "flags"), ("projects", "is_confidential")}


def check_workspace(spark, catalog: str) -> None:
    expected = WORKSPACES.get(catalog)
    actual = spark.conf.get("spark.databricks.clusterUsageTags.orgId", "")
    if not expected or actual != expected:
        raise ValueError("Migration catalog does not match the authenticated Spark workspace")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    if not volume_path(catalog).is_dir():
        raise ValueError("The existing bronze_volume/pmo_app folder must be accessible to the job identity")


def source_version(spark, table: str) -> int:
    return int(spark.sql(f"DESCRIBE HISTORY {SOURCE}.{table} LIMIT 1").first()["version"])


def export_snapshot(spark, catalog: str, snapshot: str) -> dict:
    if catalog != "automation_d":
        raise ValueError("Extraction from the original PMO catalog is allowed only in DEV")
    base = volume_path(catalog)
    name = snapshot_name(snapshot)
    folder = base / name
    archive = base / f"PMO_{name}.zip"
    if folder.exists() or archive.exists():
        raise ValueError("Snapshot already exists; use a new snapshot name instead of overwriting it")
    contract = load_contract(CONTRACT_PATH)
    inventory = {row["tableName"] for row in spark.sql(f"SHOW TABLES IN {SOURCE}").collect()}
    if inventory != set(TABLES):
        raise ValueError("The source inventory differs from the 18 reviewed PMO tables")
    versions = {table: source_version(spark, table) for table in TABLES}
    records = {}
    columns = {}
    for table in TABLES:
        frame = spark.sql(f"SELECT * FROM {SOURCE}.{table} VERSION AS OF {versions[table]}")
        columns[table] = [Column(field.name, field.dataType.simpleString(), field.nullable) for field in frame.schema.fields]
        validate_columns(table, columns[table], contract[table])
        rows = frame.orderBy("id").limit(100_001).collect()
        if len(rows) > 100_000:
            raise ValueError(f"Source table exceeds reviewed initial migration size: {table}")
        records[table] = [row.asDict() for row in rows]
    if not records["projects"] or not records["users"]:
        raise ValueError("Refusing to publish a vacuous PMO snapshot with no projects or users")
    summary = validate_records(records)
    if any(source_version(spark, table) != versions[table] for table in TABLES):
        raise ValueError("Source changed during snapshot capture; pause source writers and retry with a new name")
    folder.mkdir()
    receipts = []
    for table in TABLES:
        receipt = write_csv(folder / f"PMO_{table}.csv", columns[table],
                            (tuple(row[column.name] for column in columns[table]) for row in records[table]))
        receipts.append({"table": table, "source_version": versions[table],
                         "columns": [vars(column) for column in columns[table]], **receipt})
    manifest = {"format": FORMAT, "snapshot": name, "source": SOURCE, "source_workspace_id": WORKSPACES[catalog],
                "created_at_utc": datetime.now(timezone.utc).isoformat(), "tables": receipts,
                "authorization_summary": summary}
    with (folder / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    _, _, manifest_hash = load_snapshot(base, name, contract)
    archive_hash = package_zip(folder, archive)
    load_snapshot(base, name, contract)
    return {"status": "EXPORTED", "snapshot": name, "archive": str(archive), "folder": str(folder),
            "manifest_sha256": manifest_hash, "archive_sha256": archive_hash,
            "tables": {table: len(records[table]) for table in TABLES}, "authorization_summary": summary}


def spark_schema(columns: list[Column]):
    from pyspark.sql.types import StructType
    aliases = {"int": "integer", "bigint": "long"}
    return StructType.fromJson({"type": "struct", "fields": [
        {"name": column.name, "type": aliases.get(column.sql_type, column.sql_type), "nullable": column.nullable, "metadata": {}}
        for column in columns
    ]})


def records_frame(spark, table: str, rows: list[dict], contract: dict):
    columns = contract[table]
    transformed = [{target_column_name(table, key): value for key, value in row.items()} for row in rows]
    data = [tuple(row[column.name] for column in columns) for row in transformed]
    frame = spark.createDataFrame(data, spark_schema(columns)).cache()
    frame.count()
    return frame


def source_frames(spark, records: dict, contract: dict):
    return {table: records_frame(spark, table, records[table], contract) for table in TABLES}


def target_plan(spark, catalog: str, frames: dict, contract: dict, initial_admin: str, records: dict, baseline: dict | None = None) -> dict:
    from pyspark.sql import functions as functions
    schemas = {}
    target_counts = {}
    target_frames = {}
    for table in TABLES:
        qualified = f"{catalog}.silver.PMO_{table}"
        if not spark.catalog.tableExists(qualified):
            schemas[table] = [{"action": "create"}]
            target_counts[table] = 0
            continue
        current = spark.table(qualified)
        fields = {field.name: field for field in current.schema.fields}
        expected = {column.name: column for column in contract[table]}
        if set(fields) - set(expected):
            raise ValueError(f"Unexpected target columns: {table}")
        changes = []
        for name, column in expected.items():
            field = fields.get(name)
            if field is None:
                if (table, name) != ("users", "email_verified"):
                    raise ValueError(f"Missing target column: {table}.{name}")
                changes.append({"action": "add", "column": name})
                current = current.withColumn(name, functions.lit(None).cast(column.sql_type))
            elif field.dataType.simpleString() != column.sql_type:
                raise ValueError(f"Incompatible target column type: {table}.{name}")
            elif not field.nullable and column.nullable:
                if (table, name) not in NULLABLE_UPGRADES:
                    raise ValueError(f"Unexpected target nullability change: {table}.{name}")
                changes.append({"action": "nullable", "column": name})
        schemas[table] = changes
        target_frames[table] = current.select([column.name for column in contract[table]])
        target_counts[table] = current.count()
    bootstrap = None
    if target_counts.get("users") == 1:
        bootstrap = pristine_bootstrap_id(
            [row.asDict() for row in target_frames["users"].collect()], records["users"], initial_admin,
            sum(count for table, count in target_counts.items() if table != "users"),
        )
    for table, current in target_frames.items():
        if table == "users" and bootstrap:
            current = current.where(functions.col("id") != bootstrap)
        expected = frames[table] if baseline is None else baseline[table]
        if current.exceptAll(expected).limit(1).count():
            raise ValueError(f"Target contains changed or unrelated records; no data has been overwritten: {table}")
        if baseline is not None and expected.exceptAll(current).limit(1).count():
            raise ValueError(f"Target no longer matches the approved baseline snapshot; manual review required: {table}")
    return {"schema_changes": schemas, "existing_rows": target_counts,
            "bootstrap_id": bootstrap, "source_rows": {table: len(records[table]) for table in TABLES}}


def apply_schema(spark, catalog: str, table: str, changes: list, columns: list[Column]) -> None:
    qualified = f"{catalog}.silver.PMO_{table}"
    for change in changes:
        if change["action"] == "create":
            definitions = ", ".join(f"`{column.name}` {column.sql_type}{'' if column.nullable else ' NOT NULL'}" for column in columns)
            spark.sql(f"CREATE TABLE IF NOT EXISTS {qualified} ({definitions}) USING DELTA")
        elif change["action"] == "add":
            spark.sql(f"ALTER TABLE {qualified} ADD COLUMNS (`email_verified` TIMESTAMP)")
        elif change["action"] == "nullable":
            spark.sql(f"ALTER TABLE {qualified} ALTER COLUMN `{change['column']}` DROP NOT NULL")


def import_snapshot(spark, catalog: str, snapshot: str, mode: str, expected_hash: str, accept_authorization: bool,
                    initial_admin: str, supersedes_snapshot: str = "", supersedes_hash: str = "") -> dict:
    base = volume_path(catalog)
    contract = load_contract(CONTRACT_PATH)
    manifest, records, manifest_hash = load_snapshot(base, snapshot, contract)
    if expected_hash and expected_hash != manifest_hash:
        raise ValueError("Manifest does not match the approved export hash")
    if not records["projects"] or not records["users"]:
        raise ValueError("Refusing an empty initial PMO migration")
    if bool(supersedes_snapshot) != bool(supersedes_hash):
        raise ValueError("A resync needs both the superseded snapshot name and its approved manifest hash")
    resync = bool(supersedes_snapshot)
    if resync and (supersedes_snapshot == snapshot or supersedes_hash == manifest_hash
                   or not re.fullmatch(r"[0-9a-f]{64}", supersedes_hash)):
        raise ValueError("A resync must supersede a different, already approved snapshot")
    state_path = base / f"_PMO_initial_migration_{catalog}.json"
    previous_state = json.loads(state_path.read_text()) if state_path.exists() else None
    resuming = bool(previous_state) and previous_state.get("manifest_sha256") == manifest_hash
    if resync:
        if previous_state is None:
            raise ValueError("A resync requires the receipt of the completed import it supersedes")
        if resuming:
            if previous_state.get("supersedes_manifest_sha256") != supersedes_hash:
                raise ValueError("The interrupted migration in this environment superseded a different snapshot; manual review required")
        elif previous_state.get("manifest_sha256") != supersedes_hash or previous_state.get("status") != "COMPLETE":
            raise ValueError("This environment did not complete the snapshot this resync supersedes; manual review required")
    elif previous_state and not resuming:
        raise ValueError("This environment already started a different initial migration; manual review required")
    baseline_records = {}
    retained_records = {}
    if resync:
        _, baseline_records, baseline_hash = load_snapshot(base, supersedes_snapshot, contract)
        if baseline_hash != supersedes_hash:
            raise ValueError("The superseded package does not match its approved manifest hash")
        imported = {table: {row["id"] for row in records[table]} for table in TABLES}
        retained_records = {table: [row for row in baseline_records[table] if row["id"] not in imported[table]]
                            for table in TABLES}
    frames = source_frames(spark, records, contract)
    baseline_frames = []
    try:
        baseline = None
        retained_frames = {}
        expected_before = {}
        if resync:
            # A table already resynced by an interrupted run holds the new rows, not the superseded ones.
            done = set(previous_state.get("completed_tables", [])) if resuming else set()
            retained_frames = {table: records_frame(spark, table, retained_records[table], contract) for table in TABLES}
            baseline_frames.extend(retained_frames.values())
            baseline = {}
            for table in TABLES:
                if table in done:
                    baseline[table] = frames[table].unionByName(retained_frames[table])
                    expected_before[table] = len(records[table]) + len(retained_records[table])
                else:
                    baseline[table] = records_frame(spark, table, baseline_records[table], contract)
                    baseline_frames.append(baseline[table])
                    expected_before[table] = len(baseline_records[table])
        plan = target_plan(spark, catalog, frames, contract, initial_admin, records, baseline)
        if resync and any(plan["existing_rows"][table] != expected_before[table] for table in TABLES):
            raise ValueError("Target row counts do not match the approved baseline snapshot; manual review required")
        report = {"status": "VALIDATED", "operation": "resync" if resync else "initial", "catalog": catalog,
                  "snapshot": snapshot, "manifest_sha256": manifest_hash,
                  "source_rows": plan["source_rows"], "target_rows_before": plan["existing_rows"],
                  "schema_changes": plan["schema_changes"], "replace_pristine_bootstrap": bool(plan["bootstrap_id"]),
                  "authorization_summary": manifest["authorization_summary"]}
        if resync:
            report["supersedes"] = {"snapshot": supersedes_snapshot, "manifest_sha256": supersedes_hash}
            report["retained_rows_absent_from_source"] = {table: len(rows) for table, rows in retained_records.items()}
        if mode == "validate":
            return report
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or not accept_authorization:
            raise ValueError("Apply requires the approved manifest_sha256 and accept_user_authorization=true")
        source_admins = [row for row in records["users"] if (row.get("email") or "").lower() == initial_admin]
        if len(source_admins) != 1 or source_admins[0]["global_role"] != "ADMIN" or source_admins[0]["is_active"] is not True:
            raise ValueError("Snapshot must retain the configured initial administrator as active ADMIN")
        state = previous_state if resuming else {"catalog": catalog, "snapshot": snapshot, "manifest_sha256": manifest_hash,
                                                 "started_at_utc": datetime.now(timezone.utc).isoformat(), "completed_tables": []}
        if not resuming:
            if resync:
                state["supersedes_snapshot"] = supersedes_snapshot
                state["supersedes_manifest_sha256"] = supersedes_hash
                state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            else:
                with state_path.open("x", encoding="utf-8") as handle:
                    json.dump(state, handle, sort_keys=True, indent=2)
        for table in TABLES:
            apply_schema(spark, catalog, table, plan["schema_changes"][table], contract[table])
        token = uuid.uuid4().hex
        for table in TABLES:
            qualified = f"{catalog}.silver.PMO_{table}"
            view = f"pmo_migration_{token}_{table}"
            frames[table].createOrReplaceTempView(view)
            statement = f"MERGE INTO {qualified} AS target USING {view} AS source ON target.id = source.id"
            if resync:
                statement += " WHEN MATCHED THEN UPDATE SET *"
            statement += " WHEN NOT MATCHED THEN INSERT *"
            parameters = {}
            if table == "users" and plan["bootstrap_id"]:
                statement += " WHEN NOT MATCHED BY SOURCE AND target.id = :bootstrap_id THEN DELETE"
                parameters["bootstrap_id"] = plan["bootstrap_id"]
            spark.sql(statement, args=parameters)
            actual = spark.table(qualified).select([column.name for column in contract[table]])
            if frames[table].exceptAll(actual).limit(1).count():
                raise ValueError(f"Post-import reconciliation failed; no unrelated data was overwritten: {table}")
            remaining = actual.exceptAll(frames[table])
            if resync:
                if remaining.exceptAll(retained_frames[table]).limit(1).count() or retained_frames[table].exceptAll(remaining).limit(1).count():
                    raise ValueError(f"Post-resync reconciliation failed; unexpected target rows remain: {table}")
            elif remaining.limit(1).count():
                raise ValueError(f"Post-import reconciliation failed; no unrelated data was overwritten: {table}")
            if table not in state["completed_tables"]:
                state["completed_tables"].append(table)
            state["status"] = "IN_PROGRESS"
            state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            spark.catalog.dropTempView(view)
            print(json.dumps({"table": f"PMO_{table}", "reconciled_rows": len(records[table]),
                              "retained_rows": len(retained_records.get(table, []))}))
        state["status"] = "COMPLETE"
        state["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return {**report, "status": "IMPORTED", "receipt": str(state_path)}
    finally:
        for frame in [*frames.values(), *baseline_frames]:
            frame.unpersist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["export", "import"])
    parser.add_argument("--migration-root")
    parser.add_argument("--catalog", required=True, choices=list(WORKSPACES))
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--mode", choices=["validate", "apply"], default="validate")
    parser.add_argument("--manifest-sha256", default="")
    parser.add_argument("--supersedes-snapshot", default="")
    parser.add_argument("--supersedes-sha256", default="")
    parser.add_argument("--accept-user-authorization", choices=["true", "false"], default="false")
    parser.add_argument("--initial-admin-email", default="mustafaarda.bicakci@etexgroup.com")
    arguments = parser.parse_args()
    if not re.fullmatch(r"[^@\s]+@etexgroup\.com", arguments.initial_admin_email):
        raise ValueError("Initial administrator must be an Etex identity")
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    check_workspace(spark, arguments.catalog)
    if arguments.operation == "export":
        result = export_snapshot(spark, arguments.catalog, arguments.snapshot)
    else:
        result = import_snapshot(spark, arguments.catalog, arguments.snapshot, arguments.mode,
                                 arguments.manifest_sha256, arguments.accept_user_authorization == "true",
                                 arguments.initial_admin_email, arguments.supersedes_snapshot,
                                 arguments.supersedes_sha256)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()