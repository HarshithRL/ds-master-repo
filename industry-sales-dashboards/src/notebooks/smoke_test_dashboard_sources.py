import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession


parser = argparse.ArgumentParser()
for parameter in ("catalog", "source-catalog", "target", "warehouse-id", "config-path"):
    parser.add_argument("--" + parameter, required=True)
args = parser.parse_args()
config_path = Path(args.config_path)
sys.path.insert(0, str(config_path.parent))

from durable_results import result_scratch_root
from industry_config import validate_environment
from smoke_results import run_smoke_checks


spark = SparkSession.builder.getOrCreate()
workspace_id = spark.conf.get("spark.databricks.clusterUsageTags.orgId")
validate_environment(args.catalog, args.source_catalog, args.target, workspace_id)
start = monotonic()


def log(stage, **details):
    print(json.dumps({"stage": stage, "at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(monotonic() - start, 3), **details}), flush=True)


log("smoke_started", target=args.target, source_row_limit=1)
for layer in ("bronze", "silver", "gold"):
    spark.sql(f"DESCRIBE SCHEMA {args.catalog}.{layer}").collect()
plans = json.loads((config_path / "dashboard_results.json").read_text())["datasets"]
schemas = json.loads((config_path / "source_column_names.json").read_text())
mapping = json.loads((config_path / "cs_team_sales_org_mapping.json").read_text())["rows"]
scratch = result_scratch_root(args.catalog, args.target, uuid4().hex)
scratch.mkdir(parents=True, exist_ok=False)
run_smoke_checks(spark, WorkspaceClient(), args.warehouse_id, plans, schemas, mapping, args.source_catalog, scratch, workspace_id, log)