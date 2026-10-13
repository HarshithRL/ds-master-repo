import argparse
import hashlib
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat


ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/Workspace/Users/mustafaarda.bicakci@etexgroup.com/DS-Master-Repo/industry-sales-dashboards"
EXCLUDED = {".databricks", "__pycache__", "validation", ".venv-allocation"}
DEV_HOST = "https://adb-7181820732839861.1.azuredatabricks.net"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="DEFAULT", choices=("DEFAULT",))
    parser.add_argument("--files", nargs="+")
    args = parser.parse_args()
    workspace = WorkspaceClient(profile=args.profile)
    if workspace.config.host.rstrip("/") != DEV_HOST:
        raise ValueError("Master source uploads are DEV-only")
    manifest = []
    selected = [ROOT / relative for relative in args.files] if args.files else ROOT.rglob("*")
    for local in sorted(selected):
        relative = local.relative_to(ROOT)
        if ".." in relative.parts:
            raise ValueError(f"Path outside project: {relative}")
        if not local.is_file() or any(part in EXCLUDED for part in relative.parts):
            continue
        if local.suffix == ".pyc":
            continue
        remote = f"{REMOTE}/{relative.as_posix()}"
        content = local.read_bytes()
        workspace.workspace.mkdirs(str(Path(remote).parent))
        import_format = ImportFormat.RAW if local.suffix == ".py" else ImportFormat.AUTO
        workspace.workspace.upload(remote, content, format=import_format, overwrite=True)
        actual = workspace.workspace.download(remote).read()
        if actual != content:
            raise ValueError(f"Remote byte verification failed: {relative}")
        manifest.append({"path": relative.as_posix(), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        print(f"Verified {relative}", flush=True)
    destination = ROOT / "validation" / "master_source_upload.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"remote_root": REMOTE, "files": manifest}, indent=2) + "\n")
    print(f"Uploaded and byte-verified {len(manifest)} files; no Git commit or environment deployment performed")


if __name__ == "__main__":
    main()