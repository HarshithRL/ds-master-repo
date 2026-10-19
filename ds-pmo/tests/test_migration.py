import importlib.util
import hashlib
import json
import math
import sys
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "migration" / "transfer.py"
SPEC = importlib.util.spec_from_file_location("pmo_transfer", MODULE_PATH)
transfer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = transfer
SPEC.loader.exec_module(transfer)
CONTRACT_PATH = MODULE_PATH.with_name("table_contract.json")
RUN_SPEC = importlib.util.spec_from_file_location("pmo_migration_run", MODULE_PATH.with_name("run.py"))
runner = importlib.util.module_from_spec(RUN_SPEC)
sys.modules[RUN_SPEC.name] = runner
sys.modules["transfer"] = transfer
RUN_SPEC.loader.exec_module(runner)


def package_fixture(base: Path, name: str = "validation", flat: bool = False):
    contract = transfer.load_contract(CONTRACT_PATH)
    records = {table: [] for table in transfer.TABLES}
    user = {}
    for column in contract["users"]:
        user[column.name] = None if column.nullable else {
            "string": "fixture", "timestamp": datetime(2026, 10, 19), "boolean": True,
        }[column.sql_type]
    user.update(id="source-admin", email="admin@etexgroup.com", global_role="ADMIN", permissions="[]")
    records["users"].append(user)
    folder = base if flat else base / name
    if not flat:
        folder.mkdir()
    entries = []
    for table in transfer.TABLES:
        columns = [transfer.Column("current_bac" if column.name == "current_b_a_c" else column.name,
                                   column.sql_type, column.nullable) for column in contract[table]]
        receipt = transfer.write_csv(folder / f"PMO_{table}.csv", columns,
                                     (tuple(row[column.name] for column in columns) for row in records[table]))
        entries.append({"table": table, "source_version": 4, "columns": [vars(column) for column in columns], **receipt})
    manifest = {"format": transfer.FORMAT, "source": "engineering_global_pmo_s.pmo", "snapshot": name,
                "tables": entries, "authorization_summary": transfer.validate_records(records)}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder, contract, records, manifest


class TransferTests(unittest.TestCase):
    def test_flat_volume_layout_reads_the_same_snapshot_without_moving_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            folder, contract, records, manifest = package_fixture(base, flat=True)
            original_files = {path.name for path in base.iterdir()}
            actual_manifest, actual, fingerprint = transfer.load_snapshot(base, "validation", contract)
            self.assertEqual(actual_manifest, manifest)
            self.assertEqual(actual, records)
            self.assertEqual(fingerprint, hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest())
            self.assertEqual({path.name for path in base.iterdir()}, original_files)

    def test_flat_layout_can_be_read_again_with_the_import_receipt_present(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _, contract, records, _ = package_fixture(base, flat=True)
            (base / "_PMO_initial_migration_automation_p.json").write_text('{"status":"COMPLETE"}')
            self.assertEqual(transfer.load_snapshot(base, "validation", contract)[1], records)

    def test_flat_layout_still_rejects_missing_manifest_csv_tampering_and_unknown_files(self):
        for mutation in ["manifest", "missing_csv", "changed_csv", "extra_csv", "snapshot_name", "directory", "symlink"]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                _, contract, _, _ = package_fixture(base, flat=True)
                if mutation == "manifest":
                    (base / "manifest.json").unlink()
                elif mutation == "missing_csv":
                    (base / "PMO_users.csv").unlink()
                elif mutation == "changed_csv":
                    path = base / "PMO_users.csv"
                    path.write_bytes(path.read_bytes() + b"changed")
                elif mutation == "extra_csv":
                    (base / "PMO_unexpected.csv").write_text("extra")
                elif mutation == "directory":
                    (base / "PMO_users.csv").unlink()
                    (base / "PMO_users.csv").mkdir()
                elif mutation == "symlink":
                    (base / "PMO_users.csv").unlink()
                    (base / "PMO_users.csv").symlink_to(base / "PMO_projects.csv")
                with self.assertRaises(ValueError):
                    transfer.load_snapshot(base, "different_snapshot" if mutation == "snapshot_name" else "validation", contract)

    def test_existing_invalid_zip_or_snapshot_subfolder_cannot_fall_back_to_flat_files(self):
        for layout in ["zip", "subfolder"]:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                _, contract, _, _ = package_fixture(base, flat=True)
                if layout == "zip":
                    with zipfile.ZipFile(base / "PMO_validation.zip", "w") as archive:
                        archive.writestr("manifest.json", "{}")
                else:
                    (base / "validation").mkdir()
                with self.assertRaises(ValueError):
                    transfer.load_snapshot(base, "validation", contract)

    def test_extraction_is_dev_only_before_any_source_query(self):
        spark = MagicMock()
        for catalog in ["automation_a", "automation_p"]:
            with self.assertRaisesRegex(ValueError, "only in DEV"):
                runner.export_snapshot(spark, catalog, "fixture")
        spark.sql.assert_not_called()

    def test_workspace_mismatch_is_rejected_and_valid_run_uses_existing_volume_only(self):
        spark = MagicMock()
        spark.conf.get.return_value = "7181820732839861"
        with self.assertRaisesRegex(ValueError, "does not match"):
            runner.check_workspace(spark, "automation_a")
        spark.conf.set.assert_not_called()
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "volume_path", return_value=Path(directory)):
            runner.check_workspace(spark, "automation_d")
            spark.conf.set.assert_called_once_with("spark.sql.session.timeZone", "UTC")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_source_version_changes_prevent_publication_of_a_mixed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            _, contract, records, _ = package_fixture(base)
            project = {}
            for column in contract["projects"]:
                project[column.name] = None if column.nullable else {
                    "string": "fixture", "timestamp": datetime(2026, 10, 19), "boolean": True,
                }[column.sql_type]
            project["id"] = "project"
            records["projects"] = [project]
            spark = MagicMock()

            def source_sql(statement):
                result = MagicMock()
                if statement.startswith("SHOW TABLES"):
                    result.collect.return_value = [{"tableName": table} for table in transfer.TABLES]
                    return result
                table = statement.split()[3].rsplit(".", 1)[-1]
                result.schema.fields = [SimpleNamespace(
                    name="current_bac" if column.name == "current_b_a_c" else column.name,
                    dataType=SimpleNamespace(simpleString=lambda sql_type=column.sql_type: sql_type),
                    nullable=column.nullable) for column in contract[table]]
                result.orderBy.return_value.limit.return_value.collect.return_value = [
                    SimpleNamespace(asDict=lambda row=row: row) for row in records[table]
                ]
                return result

            spark.sql.side_effect = source_sql
            with patch.object(runner, "volume_path", return_value=base), \
                 patch.object(runner, "load_contract", return_value=contract), \
                 patch.object(runner, "source_version", side_effect=[4] * 18 + [5]):
                with self.assertRaisesRegex(ValueError, "Source changed during snapshot"):
                    runner.export_snapshot(spark, "automation_d", "changed_source")
            self.assertFalse((base / "changed_source").exists())
            self.assertFalse((base / "PMO_changed_source.zip").exists())

    def test_databricks_exec_without_dunder_file_uses_explicit_migration_root(self):
        namespace = {"__name__": "pmo_databricks_exec"}
        with patch.object(sys, "argv", ["run.py", "export", "--migration-root", str(MODULE_PATH.parent)]):
            exec(compile(MODULE_PATH.with_name("run.py").read_text(), str(MODULE_PATH.with_name("run.py")), "exec"), namespace)
        self.assertEqual(namespace["CONTRACT_PATH"], CONTRACT_PATH)
        self.assertEqual(set(namespace["load_contract"](namespace["CONTRACT_PATH"])), set(transfer.TABLES))

    def test_validate_mode_and_missing_apply_approval_never_issue_target_sql(self):
        for mode, expected_hash, approved in [("validate", "", False), ("apply", "", True), ("apply", "a" * 64, False)]:
            with tempfile.TemporaryDirectory() as directory:
                records = {table: [] for table in transfer.TABLES}
                records["users"] = [{"id": "admin", "email": "admin@etexgroup.com", "global_role": "ADMIN", "is_active": True}]
                records["projects"] = [{"id": "project"}]
                frames = {table: MagicMock() for table in transfer.TABLES}
                plan = {"schema_changes": {table: [] for table in transfer.TABLES}, "existing_rows": {},
                        "source_rows": {table: len(rows) for table, rows in records.items()}, "bootstrap_id": None}
                spark = MagicMock()
                with patch.object(runner, "volume_path", return_value=Path(directory)), \
                     patch.object(runner, "load_contract", return_value={}), \
                     patch.object(runner, "load_snapshot", return_value=({"authorization_summary": {}}, records, "a" * 64)), \
                     patch.object(runner, "source_frames", return_value=frames), \
                     patch.object(runner, "target_plan", return_value=plan):
                    if mode == "validate":
                        result = runner.import_snapshot(spark, "automation_a", "fixture", mode, expected_hash, approved, "admin@etexgroup.com")
                        self.assertEqual(result["status"], "VALIDATED")
                    else:
                        with self.assertRaisesRegex(ValueError, "Apply requires"):
                            runner.import_snapshot(spark, "automation_a", "fixture", mode, expected_hash, approved, "admin@etexgroup.com")
                spark.sql.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])
                for frame in frames.values():
                    frame.unpersist.assert_called_once()

    def test_apply_uses_insert_only_merges_exact_receipts_and_rejects_a_different_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            records = {table: [] for table in transfer.TABLES}
            records["users"] = [{"id": "admin", "email": "admin@etexgroup.com", "global_role": "ADMIN", "is_active": True}]
            records["projects"] = [{"id": "project"}]
            frames = {table: MagicMock() for table in transfer.TABLES}
            for frame in frames.values():
                frame.exceptAll.return_value.limit.return_value.count.return_value = 0
            plan = {"schema_changes": {table: [] for table in transfer.TABLES}, "existing_rows": {},
                    "source_rows": {table: len(rows) for table, rows in records.items()}, "bootstrap_id": "unused-bootstrap"}
            spark = MagicMock()
            spark.table.return_value.select.return_value.exceptAll.return_value.limit.return_value.count.return_value = 0
            contract = {table: [transfer.Column("id", "string", False)] for table in transfer.TABLES}
            with patch.object(runner, "volume_path", return_value=Path(directory)), \
                 patch.object(runner, "load_contract", return_value=contract), \
                 patch.object(runner, "load_snapshot", return_value=({"authorization_summary": {}}, records, "a" * 64)), \
                 patch.object(runner, "source_frames", return_value=frames), \
                 patch.object(runner, "target_plan", return_value=plan), \
                 patch("builtins.print"):
                result = runner.import_snapshot(spark, "automation_a", "fixture", "apply", "a" * 64, True, "admin@etexgroup.com")
                self.assertEqual(result["status"], "IMPORTED")
            statements = [call.args[0] for call in spark.sql.call_args_list]
            self.assertEqual(len(statements), 18)
            self.assertTrue(all(statement.startswith("MERGE INTO automation_a.silver.PMO_") for statement in statements))
            self.assertTrue(all("WHEN NOT MATCHED THEN INSERT *" in statement for statement in statements))
            self.assertTrue(all("UPDATE" not in statement for statement in statements))
            self.assertEqual(sum("THEN DELETE" in statement for statement in statements), 1)
            self.assertIn("target.id = :bootstrap_id THEN DELETE", statements[0])
            self.assertEqual(spark.sql.call_args_list[0].kwargs["args"], {"bootstrap_id": "unused-bootstrap"})
            receipt = json.loads(Path(result["receipt"]).read_text())
            self.assertEqual(receipt["status"], "COMPLETE")
            self.assertEqual(receipt["completed_tables"], list(transfer.TABLES))
            with patch.object(runner, "volume_path", return_value=Path(directory)), \
                 patch.object(runner, "load_contract", return_value=contract), \
                 patch.object(runner, "load_snapshot", return_value=({"authorization_summary": {}}, records, "b" * 64)), \
                 patch.object(runner, "source_frames") as create_frames:
                with self.assertRaisesRegex(ValueError, "different initial migration"):
                    runner.import_snapshot(spark, "automation_a", "other", "apply", "b" * 64, True, "admin@etexgroup.com")
                create_frames.assert_not_called()

    def test_complete_snapshot_and_portable_zip_have_identical_rows_and_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            folder, contract, records, manifest = package_fixture(base)
            actual_manifest, actual, fingerprint = transfer.load_snapshot(base, "validation", contract)
            self.assertEqual(actual, records)
            self.assertEqual(actual_manifest, manifest)
            self.assertEqual(fingerprint, hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest())
            transfer.package_zip(folder, base / "PMO_validation.zip")
            self.assertEqual(transfer.load_snapshot(base, "validation", contract)[1:], (records, fingerprint))

    def test_modified_or_missing_csv_is_rejected_before_any_target_access(self):
        for mutation in ["modified", "missing"]:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                folder, contract, _, _ = package_fixture(base)
                path = folder / "PMO_users.csv"
                if mutation == "modified":
                    path.write_bytes(path.read_bytes() + b"changed")
                else:
                    path.unlink()
                with self.assertRaises(ValueError):
                    transfer.load_snapshot(base, "validation", contract)

    def test_manifest_counts_unknown_columns_and_permission_summary_cannot_be_forged(self):
        for mutation in ["row_count", "column", "permissions", "table_count"]:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                folder, contract, _, manifest = package_fixture(base)
                if mutation == "row_count":
                    manifest["tables"][0]["rows"] += 1
                elif mutation == "column":
                    manifest["tables"][0]["columns"][0]["name"] = "different_id"
                elif mutation == "permissions":
                    manifest["authorization_summary"]["active_users"] += 1
                else:
                    manifest["tables"].pop()
                (folder / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    transfer.load_snapshot(base, "validation", contract)

    def test_zip_path_traversal_or_extra_files_are_rejected_without_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            folder, contract, _, _ = package_fixture(base)
            transfer.package_zip(folder, base / "PMO_validation.zip")
            with zipfile.ZipFile(base / "PMO_validation.zip", "a") as archive:
                archive.writestr("../outside.csv", "malicious")
            with self.assertRaises(ValueError):
                transfer.load_snapshot(base, "validation", contract)
            self.assertFalse((base.parent / "outside.csv").exists())

    def test_duplicate_ids_roles_permissions_and_dangling_current_relations_are_rejected(self):
        for mutation in ["id", "role", "permission", "relationship", "domain"]:
            with tempfile.TemporaryDirectory() as directory:
                _, _, records, _ = package_fixture(Path(directory))
                if mutation == "id":
                    records["users"].append(dict(records["users"][0]))
                elif mutation == "role":
                    records["users"][0]["global_role"] = "SUPERUSER"
                elif mutation == "permission":
                    records["users"][0]["permissions"] = '["ALL_PRIVILEGES"]'
                elif mutation == "domain":
                    records["users"][0]["email"] = "other@example.com"
                else:
                    records["project_assignments"].append({"id": "assignment", "user_id": "source-admin", "project_id": "missing"})
                with self.assertRaises(ValueError):
                    transfer.validate_records(records)

    def test_historical_audit_references_are_preserved_and_reported_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, records, _ = package_fixture(Path(directory))
            records["audit_logs"].append({"id": "audit", "project_id": "deleted-project", "user_id": "former-user"})
            summary = transfer.validate_records(records)
            self.assertEqual(summary["historical_missing_references"]["audit_logs.project_id"], 1)
            self.assertEqual(summary["historical_missing_references"]["audit_logs.user_id"], 1)
            self.assertEqual(len(records["audit_logs"]), 1)

    def test_pristine_bootstrap_can_be_replaced_but_used_or_unrelated_users_cannot(self):
        timestamp = datetime(2026, 10, 19)
        email = "admin@etexgroup.com"
        bootstrap = {"id": "new-id", "email": email, "name": email, "global_role": "ADMIN", "permissions": "[]",
                     "is_active": True, "created_at": timestamp, "updated_at": timestamp}
        source = [{"id": "original-id", "email": email, "global_role": "ADMIN", "is_active": True}]
        self.assertEqual(transfer.pristine_bootstrap_id([bootstrap], source, email, 0), "new-id")
        self.assertIsNone(transfer.pristine_bootstrap_id([bootstrap], source, email, 1))
        self.assertIsNone(transfer.pristine_bootstrap_id([{**bootstrap, "name": "Edited"}], source, email, 0))
        self.assertIsNone(transfer.pristine_bootstrap_id([{**bootstrap, "last_login_at": timestamp}], source, email, 0))
        self.assertIsNone(transfer.pristine_bootstrap_id([bootstrap], [{**source[0], "is_active": False}], email, 0))

    def test_paths_and_unknown_catalogs_cannot_escape_the_migration_folder(self):
        for value in ["../other", "/tmp/file", "name/child", "", "a" * 65]:
            with self.assertRaises(ValueError):
                transfer.snapshot_name(value)
        for value in ["engineering_global_pmo_s", "automation_x", "automation_a;DROP TABLE"]:
            with self.assertRaises(ValueError):
                transfer.volume_path(value)
        self.assertEqual(str(transfer.volume_path("automation_p")), "/Volumes/automation_p/bronze/bronze_volume/pmo_app")

    def test_only_documented_snapshot_column_alias_is_mapped(self):
        self.assertEqual(transfer.target_column_name("project_snapshots", "current_bac"), "current_b_a_c")
        self.assertEqual(transfer.target_column_name("users", "email_verified"), "email_verified")
        self.assertEqual(transfer.target_column_name("projects", "name"), "name")
        with self.assertRaises(ValueError):
            transfer.target_column_name("unknown", "id")

    def test_csv_roundtrip_preserves_null_empty_multiline_json_and_formulas(self):
        columns = [transfer.Column("id", "string", False), transfer.Column("text", "string", True)]
        rows = [("1", None), ("2", ""), ("3", "null"), ("4", "first\nsecond,\"quoted\"\r\nthird"),
                ("5", '{"permissions":["MANAGE_USERS"]}'), ("6", '=HYPERLINK("https://example.com")'),
                ("7", "\u0130stanbul \u00e9"), ("8", "\\N")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PMO_users.csv"
            receipt = transfer.write_csv(path, columns, rows)
            self.assertEqual(list(transfer.read_csv(path, columns)), rows)
            self.assertEqual(receipt["rows"], len(rows))
            self.assertEqual(receipt["sha256"], transfer.sha256_file(path))
            self.assertIn('""=HYPERLINK', path.read_text())

    def test_numeric_dates_and_microseconds_roundtrip(self):
        columns = [transfer.Column("amount", "decimal(18,6)", False), transfer.Column("metric", "double", False),
                   transfer.Column("created_at", "timestamp", False), transfer.Column("active", "boolean", False),
                   transfer.Column("day", "date", False), transfer.Column("count", "bigint", False)]
        rows = [(Decimal("-12345678.123456"), -0.0, datetime(2026, 10, 19, 12, 34, 56, 123456), True,
                 date(2026, 10, 19), 9223372036854775807)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PMO_metrics.csv"
            transfer.write_csv(path, columns, rows)
            self.assertEqual(list(transfer.read_csv(path, columns)), rows)

    def test_timezone_is_normalized_to_utc_and_nonfinite_floats_are_preserved(self):
        column = transfer.Column("stamp", "timestamp", False)
        value = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
        self.assertEqual(transfer.decode_cell(transfer.encode_cell(value, column), column), value.replace(tzinfo=None))
        metric = transfer.Column("metric", "double", False)
        self.assertTrue(math.isnan(transfer.decode_cell(transfer.encode_cell(float("nan"), metric), metric)))
        for value in [float("inf"), float("-inf")]:
            self.assertEqual(transfer.decode_cell(transfer.encode_cell(value, metric), metric), value)

    def test_invalid_types_required_nulls_and_schema_identifiers_are_rejected(self):
        for kind, value in [("int", True), ("boolean", 1), ("string", 3), ("timestamp", "not-a-date")]:
            with self.assertRaises((ValueError, TypeError)):
                transfer.encode_cell(value, transfer.Column("value", kind, False))
        with self.assertRaises(ValueError):
            transfer.encode_cell(None, transfer.Column("id", "string", False))
        with self.assertRaises(ValueError):
            transfer.Column("id;drop", "string", False)
        with self.assertRaises(ValueError):
            transfer.Column("id", "map<string,string>", False)

    def test_reexport_cannot_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PMO_users.csv"
            columns = [transfer.Column("id", "string", False)]
            transfer.write_csv(path, columns, [("first",)])
            with self.assertRaises(FileExistsError):
                transfer.write_csv(path, columns, [("second",)])
            self.assertEqual(list(transfer.read_csv(path, columns)), [("first",)])


if __name__ == "__main__":
    unittest.main()