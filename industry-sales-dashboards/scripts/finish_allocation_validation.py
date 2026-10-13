import json
import sys
from datetime import timedelta
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import OperationFailed


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from industry_config import DEV_VALIDATION_HOST, validate_dev_validation_job


def main():
    receipt = json.loads((ROOT / "validation/allocation_validation_run.json").read_text())
    validate_dev_validation_job(DEV_VALIDATION_HOST, receipt["job_id"])
    if receipt.get("profile") != "DEFAULT":
        raise ValueError("Only an explicit DEV validation receipt may be processed")
    workspace = WorkspaceClient(profile="DEFAULT")
    validate_dev_validation_job(workspace.config.host, receipt["job_id"])
    run_id = receipt["run_id"]
    try:
        workspace.jobs.wait_get_run_job_terminated_or_skipped(run_id=run_id, timeout=timedelta(minutes=22))
    except TimeoutError:
        print("Validation budget expired; canceling only the candidate run", flush=True)
        workspace.jobs.cancel_run(run_id).result(timeout=timedelta(minutes=5))
    except OperationFailed as error:
        print(str(error), flush=True)
    finally:
        run = workspace.jobs.get_run(run_id).as_dict()
        (ROOT / "validation/allocation_validation_result.json").write_text(json.dumps(run, indent=2) + "\n")
        (ROOT / f"validation/allocation_validation_result_{run_id}.json").write_text(json.dumps(run, indent=2) + "\n")
        tasks = [task for task in run.get("tasks", []) if task["task_key"] == receipt["temporary_task_key"]]
        print(json.dumps({"run_id": run_id, "state": run.get("state"), "tasks": [{"run_id": task["run_id"], "state": task["state"]} for task in tasks]}, indent=2), flush=True)
        for task in tasks:
            output = workspace.jobs.get_run_output(task["run_id"]).as_dict()
            (ROOT / "validation/allocation_validation_output.json").write_text(json.dumps(output, indent=2) + "\n")
            print(json.dumps({"error": output.get("error"), "logs": (output.get("logs") or "")[-6000:]}, indent=2), flush=True)
        if run.get("state", {}).get("life_cycle_state") in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            settings = workspace.jobs.get(receipt["job_id"]).as_dict()["settings"]
            current = next((task for task in settings["tasks"] if task["task_key"] == receipt["temporary_task_key"]), None)
            if current is not None:
                if not current.get("spark_python_task", {}).get("python_file", "").startswith(receipt["source_root"] + "/"):
                    raise ValueError("Temporary task belongs to a different validation run; refusing cleanup")
                workspace.api_client.do("POST", "/api/2.1/jobs/update", body={"job_id": receipt["job_id"], "fields_to_remove": ["tasks/" + receipt["temporary_task_key"]]})
                print("Removed temporary validation task", flush=True)
            else:
                print("Temporary validation task already removed", flush=True)


if __name__ == "__main__":
    main()