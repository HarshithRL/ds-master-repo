import json
from pathlib import Path

from databricks.sdk import WorkspaceClient


ROOT = Path(__file__).resolve().parents[1]


def main():
    workspace = WorkspaceClient(profile="DEFAULT")
    if workspace.config.host.rstrip("/") != "https://adb-7181820732839861.1.azuredatabricks.net":
        raise ValueError("Source metadata capture is DEV-only")
    sources = json.loads((ROOT / "src/config/source_dependencies.json").read_text())["pbi_tables"]
    schemas = {}
    for name in sources:
        table = workspace.tables.get("synapse-prd.pbi." + name)
        schemas[name] = [column.name for column in table.columns]
        print(f"Captured DEV column names: {name}: {len(schemas[name])}", flush=True)
    destination = ROOT / "src/config/source_column_names.json"
    destination.write_text(json.dumps(schemas, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()