import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIR))


class RecordingSpark:
    def __init__(self):
        self.statements = []
        self.rows = None
        self.saved_table = None

    def sql(self, statement):
        self.statements.append(statement)

    def createDataFrame(self, rows, schema):
        self.rows = rows
        self.schema = schema
        return RecordingDataFrame(self)


class RecordingDataFrame:
    def __init__(self, spark):
        self.write = RecordingWriter(spark)


class RecordingWriter:
    def __init__(self, spark):
        self.spark = spark

    def format(self, value):
        self.format_name = value
        return self

    def mode(self, value):
        self.mode_name = value
        return self

    def option(self, name, value):
        return self

    def saveAsTable(self, table):
        self.spark.saved_table = table


class FakeBuilder:
    spark = None

    def getOrCreate(self):
        return self.spark


class FakeSparkSession:
    builder = FakeBuilder()


fake_pyspark = types.ModuleType("pyspark")
fake_pyspark_sql = types.ModuleType("pyspark.sql")
fake_pyspark_sql.SparkSession = FakeSparkSession
fake_pyspark.sql = fake_pyspark_sql
with patch.dict(sys.modules, {"pyspark": fake_pyspark, "pyspark.sql": fake_pyspark_sql}):
    from setup_tables import (
        CONFIGURATION_FILES,
        load_configuration_snapshot,
        main,
        validate_production_configuration,
    )


class FakeWorksheet:
    def __init__(self, title, rows):
        self.title = title
        self.rows = rows

    def iter_rows(self, values_only=False):
        return iter(self.rows)


class FakeWorkbook:
    def __init__(self, worksheets):
        self.worksheets = worksheets
        self.sheetnames = [worksheet.title for worksheet in worksheets]

    def close(self):
        pass


class SetupTablesTests(unittest.TestCase):
    def test_creates_app_tables_and_overwrites_configuration_snapshot(self):
        spark = RecordingSpark()
        FakeBuilder.spark = spark

        snapshot = [("assignment_rules.xlsx", "Members", "[]", "sha", None)]
        config_directory = "/Volumes/automation_a/bronze/bronze_volume/master_data_app"
        observed = {}

        def fake_load_configuration_snapshot(directory, catalog):
            observed["directory"] = str(directory)
            observed["catalog"] = catalog
            return snapshot, 0

        with patch.dict(
            main.__globals__,
            {"load_configuration_snapshot": fake_load_configuration_snapshot, "__file__": None},
        ):
            main("automation_d", config_directory)

        self.assertEqual(observed, {"directory": config_directory, "catalog": "automation_d"})
        self.assertEqual(len(spark.statements), 3)
        self.assertIn("automation_d.bronze.master_data_app_requests", spark.statements[0])
        self.assertIn("automation_d.bronze.master_data_app_request_history", spark.statements[1])
        self.assertIn("automation_d.bronze.master_data_app_configuration", spark.statements[2])
        self.assertTrue(all("CREATE SCHEMA" not in statement.upper() for statement in spark.statements))
        self.assertEqual(spark.saved_table, "automation_d.bronze.master_data_app_configuration")
        self.assertEqual(spark.rows, snapshot)

    def test_configuration_directory_is_required(self):
        spark = RecordingSpark()
        FakeBuilder.spark = spark

        with self.assertRaisesRegex(ValueError, "configuration directory must be supplied"):
            main("automation_d", "")

        self.assertEqual(spark.statements, [])

    def test_rejects_catalog_outside_the_automation_environments(self):
        with self.assertRaises(ValueError):
            main("automation_custom", "/Volumes/automation_d/bronze/bronze_volume/master_data_app")

    def test_blocks_test_only_configuration_in_acceptance_and_production(self):
        for catalog in ("automation_a", "automation_p"):
            with self.subTest(catalog=catalog):
                with self.assertRaisesRegex(ValueError, "test-only or dummy"):
                    validate_production_configuration(catalog, ["TEST ONLY dummy configuration"])

    def test_allows_development_configuration(self):
        validate_production_configuration("automation_d", ["TEST ONLY dummy configuration"])

    def test_seed_blocker_reports_source_and_cell_before_any_table_write(self):
        spark = RecordingSpark()
        FakeBuilder.spark = spark
        workbook_data = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file_name, required_sheets in CONFIGURATION_FILES.items():
                (root / file_name).write_bytes(file_name.encode("ascii"))
                worksheets = [
                    FakeWorksheet(
                        sheet,
                        [("field", "notes"), ("sample", "TEST ONLY dummy configuration")]
                        if file_name == "customer_form_rules.xlsx" and sheet == "Form_Fields"
                        else [("field", "notes"), ("sample", "approved")],
                    )
                    for sheet in required_sheets
                ]
                workbook_data[file_name] = FakeWorkbook(worksheets)

            openpyxl = types.ModuleType("openpyxl")
            openpyxl.load_workbook = lambda path, **_kwargs: workbook_data[Path(path).name]
            with patch.dict(sys.modules, {"openpyxl": openpyxl}):
                for catalog in ("automation_a", "automation_p"):
                    with self.subTest(catalog=catalog):
                        with self.assertRaises(ValueError) as raised:
                            main(catalog, root)
                        message = str(raised.exception)
                        self.assertIn(str(root), message)
                        self.assertIn("Found 1 blocked cells", message)
                        self.assertIn("customer_form_rules.xlsx/Form_Fields: row 2, column notes", message)

        self.assertEqual(spark.statements, [])
        self.assertIsNone(spark.saved_table)

    def test_snapshot_preserves_every_sheet_and_serializes_required_rows(self):
        workbook_data = {}
        expected_sheet_count = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file_name, required_sheets in CONFIGURATION_FILES.items():
                (root / file_name).write_bytes(file_name.encode("ascii"))
                worksheets = [
                    FakeWorksheet(sheet, [("field", "value"), ("sample", "ok")])
                    for sheet in required_sheets
                ]
                worksheets.append(
                    FakeWorksheet("README", [("section", "notes"), ("Purpose", "dummy rules")])
                )
                workbook_data[file_name] = FakeWorkbook(worksheets)
                expected_sheet_count += len(worksheets)

            openpyxl = types.ModuleType("openpyxl")
            openpyxl.load_workbook = lambda path, **_kwargs: workbook_data[Path(path).name]
            with patch.dict(sys.modules, {"openpyxl": openpyxl}):
                snapshot, source_row_count = load_configuration_snapshot(root, "automation_d")

        self.assertEqual(len(snapshot), expected_sheet_count)
        self.assertEqual(source_row_count, sum(len(book.worksheets) * 1 for book in workbook_data.values()))
        reference_row = next(
            row
            for row in snapshot
            if row[0] == "general_data.xlsx"
            and row[1] == "General_Data_Fields"
        )
        self.assertEqual(json.loads(reference_row[2]), [{"field": "sample", "value": "ok"}])

    def test_empty_required_sheet_stops_before_table_creation(self):
        spark = RecordingSpark()
        FakeBuilder.spark = spark
        workbook_data = {}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file_index, (file_name, required_sheets) in enumerate(CONFIGURATION_FILES.items()):
                (root / file_name).write_bytes(file_name.encode("ascii"))
                worksheets = [
                    FakeWorksheet(
                        sheet,
                        [] if file_index == 0 and sheet == "General_Data_Fields"
                        else [("field", "value"), ("sample", "ok")],
                    )
                    for sheet in required_sheets
                ]
                workbook_data[file_name] = FakeWorkbook(worksheets)

            openpyxl = types.ModuleType("openpyxl")
            openpyxl.load_workbook = lambda path, **_kwargs: workbook_data[Path(path).name]
            with patch.dict(sys.modules, {"openpyxl": openpyxl}):
                with self.assertRaisesRegex(ValueError, "has no data rows"):
                    main("automation_d", root)

        self.assertEqual(spark.statements, [])

    def test_reference_workbook_supports_legacy_volume_name_and_prefers_latest(self):
        for include_latest in (False, True):
            with self.subTest(include_latest=include_latest), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workbook_data = {}
                for file_name, sheets in CONFIGURATION_FILES.items():
                    (root / file_name).write_bytes(file_name.encode("ascii"))
                    workbook_data[file_name] = FakeWorkbook([
                        FakeWorksheet(sheet, [("field", "value"), ("sample", "approved")])
                        for sheet in sheets
                    ])
                legacy_name = "customer_reference_library.xlsx"
                (root / legacy_name).write_bytes(b"legacy reference workbook")
                workbook_data[legacy_name] = workbook_data["general_data.xlsx"]
                if not include_latest:
                    (root / "general_data.xlsx").unlink()
                openpyxl = types.ModuleType("openpyxl")
                openpyxl.load_workbook = lambda path, **_kwargs: workbook_data[Path(path).name]
                with patch.dict(sys.modules, {"openpyxl": openpyxl}):
                    snapshot, _ = load_configuration_snapshot(root, "automation_a")
                expected = "general_data.xlsx" if include_latest else legacy_name
                reference_rows = [row for row in snapshot if row[1] == "General_Data_Fields"]
                self.assertEqual([row[0] for row in reference_rows], [expected])


if __name__ == "__main__":
    unittest.main()