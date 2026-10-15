import re
from pathlib import Path
from shutil import rmtree


def result_scratch_root(catalog, target, batch):
    if catalog not in {"D": "automation_d", "T": "automation_d", "A": "automation_a", "P": "automation_p"}.values():
        raise ValueError("Invalid scratch catalog")
    if target not in ("D", "T", "A", "P") or catalog != {"D": "automation_d", "T": "automation_d", "A": "automation_a", "P": "automation_p"}[target]:
        raise ValueError("Scratch catalog does not match target")
    if not re.fullmatch(r"[a-f0-9]{32}", batch):
        raise ValueError("Invalid scratch batch")
    return Path(f"/Volumes/{catalog}/bronze/bronze_volume/SC_BI_industry_sales_result_scratch/{target}/{batch}")


def result_dataset_scratch(root, dashboard, dataset):
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in (dashboard, dataset)):
        raise ValueError("Invalid scratch dataset identity")
    return Path(root) / dashboard / dataset


def stage_result_frame(spark, frame, path):
    schema = frame.schema
    settings = ("spark.sql.parquet.datetimeRebaseModeInWrite", "spark.sql.parquet.int96RebaseModeInWrite")
    previous = {name: spark.conf.get(name) for name in settings}
    try:
        for name in settings:
            spark.conf.set(name, "CORRECTED")
        frame.write.mode("errorifexists").parquet(str(path))
    finally:
        for name, value in previous.items():
            spark.conf.set(name, value)
    stored = spark.read.schema(schema).option("datetimeRebaseMode", "CORRECTED").option("int96RebaseMode", "CORRECTED").parquet(str(path))
    required = [(field.name, field.dataType) for field in schema.fields]
    actual = [(field.name, field.dataType) for field in stored.schema.fields]
    if required != actual:
        raise ValueError("Durable staging changed the native column contract")
    return stored


def cleanup_result_scratch(path):
    if Path(path).exists():
        rmtree(path)