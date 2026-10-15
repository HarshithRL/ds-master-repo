import re
from contextlib import redirect_stdout
from io import StringIO
from json import dumps
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


def failed_stage_details(frame, path, error):
    details = {"path": str(path), "error_type": type(error).__name__, "error": str(error)}
    try:
        output = StringIO()
        with redirect_stdout(output):
            frame.explain(mode="formatted")
        details["physical_plan"] = output.getvalue()
    except Exception as plan_error:
        details["plan_error"] = f"{type(plan_error).__name__}: {plan_error}"
    return details


def report_stage_failure(frame, path, error):
    details = failed_stage_details(frame, path, error)
    summary = {"stage": "scratch_write_failed", "path": str(path), "error_type": details["error_type"], "error": details["error"].splitlines()[0] if details["error"] else "", "physical_plan_chars": len(details.get("physical_plan", ""))}
    try:
        destination = Path(path).with_name(Path(path).name + ".failure.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as output:
            output.write(dumps(details))
        summary["diagnostics_path"] = str(destination)
    except Exception as diagnostic_error:
        summary["diagnostics_error"] = f"{type(diagnostic_error).__name__}: {diagnostic_error}"
    serialized = dumps(summary)
    while len(serialized.encode("utf-8")) > 8192:
        key = max((name for name, value in summary.items() if isinstance(value, str)), key=lambda name: len(summary[name]))
        text = summary[key]
        half = max(8, len(text) // 4)
        summary[key] = text[:half] + " ... " + text[-half:]
        serialized = dumps(summary)
    print(serialized, flush=True)


def stage_result_frame(spark, frame, path):
    schema = frame.schema
    settings = ("spark.sql.parquet.datetimeRebaseModeInWrite", "spark.sql.parquet.int96RebaseModeInWrite")
    previous = {name: spark.conf.get(name) for name in settings}
    try:
        for name in settings:
            spark.conf.set(name, "CORRECTED")
        try:
            frame.write.mode("error").parquet(str(path))
        except Exception as error:
            report_stage_failure(frame, path, error)
            raise
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