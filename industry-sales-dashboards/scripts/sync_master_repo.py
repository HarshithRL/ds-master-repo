import argparse
import hashlib
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat


ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/Workspace/Users/mustafaarda.bicakci@etexgroup.com/DS-Master-Repo/industry-sales-dashboards"
EXCLUDED = {".databricks", "__pycache__", "validation"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="DEFAULT")
    args = parser.parse_args()
    workspace = WorkspaceClient(profile=args.profile)
    manifest = []
    for local in sorted(ROOT.rglob("*")):
        relative = local.relative_to(ROOT)
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