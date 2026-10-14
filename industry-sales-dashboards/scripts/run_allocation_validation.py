import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from industry_config import DEV_VALIDATION_JOB_ID, validate_dev_validation_job


def main():
    workspace = WorkspaceClient(profile="DEFAULT")
    validate_dev_validation_job(workspace.config.host, DEV_VALIDATION_JOB_ID)
    original = workspace.jobs.get(DEV_VALIDATION_JOB_ID).as_dict()
    task_key = "validate_allocation_probe"
    if any(task["task_key"] == task_key for task in original["settings"]["tasks"]):
        raise ValueError("An allocation validation task already exists; inspect it before starting another")
    if next(workspace.jobs.list_runs(job_id=original["job_id"], active_only=True), None) is not None:
        raise ValueError("The DEV job has an active run; do not change its task graph")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    user_name = workspace.current_user.me().user_name
    remote_root = f"/Workspace/Users/{user_name}/industry-allocation-validation/{stamp}"
    files = (
        "src/allocation_stages.py",
        "src/industry_config.py",
        "src/source_snapshots.py",
        "src/config/open_orders_allocation.sql",
        "src/config/source_snapshots.json",
        "src/notebooks/materialize_allocation.py",
    )
    for relative in files:
        remote = f"{remote_root}/{relative}"
        content = (ROOT / relative).read_bytes()
        workspace.workspace.mkdirs(str(Path(remote).parent))
        workspace.workspace.upload(remote, content, format=ImportFormat.RAW, overwrite=False)
        if workspace.workspace.download(remote).read() != content:
            raise ValueError(f"Source byte verification failed: {relative}")
    task = {
            "task_key": task_key,
            "spark_python_task": {
                "python_file": f"{remote_root}/src/notebooks/materialize_allocation.py",
                "parameters": ["--catalog", "automation_d", "--source-catalog", "synapse-prd", "--target", "D", "--config-path", f"{remote_root}/src/config", "--mapping-table-name", "industry_sales_cs_team_sales_org_mapping_dev", "--candidate"],
            },
            "job_cluster_key": original["settings"]["job_clusters"][0]["job_cluster_key"],
            "libraries": [{"pypi": {"package": "sqlglot==27.20.0"}}],
            "timeout_seconds": 1800,
    }
    workspace.api_client.do("POST", "/api/2.1/jobs/update", body={"job_id": original["job_id"], "new_settings": {"tasks": [task]}})
    run = workspace.api_client.do("POST", "/api/2.1/jobs/run-now", body={"job_id": original["job_id"], "only": [task_key]})
    receipt = {"job_id": original["job_id"], "run_id": run["run_id"], "source_root": remote_root, "run_as": original["run_as_user_name"], "temporary_task_key": task_key, "profile": "DEFAULT"}
    destination = ROOT / "validation/allocation_validation_run.json"
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()