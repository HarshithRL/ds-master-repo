import csv
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Sequence


TABLES = (
    "users", "divisions", "factories", "categories", "resources", "projects",
    "project_assignments", "scope_grants", "budgets", "budget_lines",
    "gate_records", "risks", "milestones", "planned_actions", "scope_changes",
    "project_documents", "project_snapshots", "audit_logs",
)
FORMAT = "pmo-json-cell-csv-v1"
COLUMN_ALIASES = {"project_snapshots": {"current_bac": "current_b_a_c"}}
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
PERMISSIONS = {"MANAGE_USERS", "MANAGE_FACTORIES", "MANAGE_CATEGORIES", "MANAGE_DIVISIONS", "VIEW_AUDIT_LOGS", "MANAGE_RESOURCES"}
FOREIGN_KEYS = (
    ("factories", "division_id", "divisions"),
    ("projects", "factory_id", "factories"), ("projects", "category_id", "categories"),
    ("project_assignments", "project_id", "projects"), ("project_assignments", "user_id", "users"),
    ("scope_grants", "user_id", "users"), ("scope_grants", "division_id", "divisions"),
    ("scope_grants", "factory_id", "factories"), ("budgets", "project_id", "projects"),
    ("budget_lines", "budget_id", "budgets"), ("gate_records", "project_id", "projects"),
    ("risks", "project_id", "projects"), ("milestones", "project_id", "projects"),
    ("planned_actions", "project_id", "projects"), ("scope_changes", "project_id", "projects"),
    ("project_documents", "project_id", "projects"),
)


def target_column_name(table: str, source_column: str) -> str:
    if table not in TABLES:
        raise ValueError("Unknown PMO migration table")
    return COLUMN_ALIASES.get(table, {}).get(source_column, source_column)


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str
    nullable: bool

    def __post_init__(self) -> None:
        if type(self.nullable) is not bool:
            raise ValueError("Invalid migration nullability")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("Invalid migration column name")
        supported = r"string|boolean|byte|short|integer|int|long|bigint|float|double|date|timestamp|timestamp_ntz|decimal\([0-9]+,[0-9]+\)"
        if not re.fullmatch(supported, self.sql_type):
            raise ValueError(f"Unsupported migration type: {self.sql_type}")


def encode_cell(value: object, column: Column) -> str:
    if value is None:
        if not column.nullable:
            raise ValueError(f"NULL in required column {column.name}")
        return "null"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        value = value.isoformat(timespec="microseconds")
    elif isinstance(value, (date, Decimal)):
        value = str(value)
    elif isinstance(value, float) and not math.isfinite(value):
        value = "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    decode_cell(encoded, column)
    return encoded


def decode_cell(encoded: str, column: Column) -> object:
    value = json.loads(encoded)
    if value is None:
        if not column.nullable:
            raise ValueError(f"NULL in required column {column.name}")
        return None
    sql_type = column.sql_type
    if sql_type == "string" and isinstance(value, str):
        return value
    if sql_type == "boolean" and isinstance(value, bool):
        return value
    if sql_type in {"byte", "short", "integer", "int", "long", "bigint"} and type(value) is int:
        return value
    if sql_type in {"float", "double"}:
        if type(value) in {int, float}:
            return float(value)
        if value in ("NaN", "Infinity", "-Infinity"):
            return float(value)
    if sql_type.startswith("decimal(") and isinstance(value, str):
        decimal = Decimal(value)
        if decimal.is_finite():
            return decimal
    if sql_type == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if sql_type in {"timestamp", "timestamp_ntz"} and isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed
    raise ValueError(f"Invalid {sql_type} value in column {column.name}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, columns: Sequence[Column], rows: Iterable[Sequence[object]]) -> dict:
    count = 0
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow([column.name for column in columns])
        for row in rows:
            if len(row) != len(columns):
                raise ValueError("CSV row does not match the declared schema")
            writer.writerow([encode_cell(value, column) for value, column in zip(row, columns)])
            count += 1
    return {"file": path.name, "rows": count, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def read_csv(path: Path, columns: Sequence[Column]) -> Iterator[tuple[object, ...]]:
    csv.field_size_limit(16 * 1024 * 1024)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        if next(reader, None) != [column.name for column in columns]:
            raise ValueError("CSV header does not match the declared schema")
        for row in reader:
            if len(row) != len(columns):
                raise ValueError("CSV row does not match the declared schema")
            yield tuple(decode_cell(value, column) for value, column in zip(row, columns))


def snapshot_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("Snapshot must be a simple folder name, without a path")
    return value


def volume_path(catalog: str) -> Path:
    if catalog not in {"automation_d", "automation_a", "automation_p"}:
        raise ValueError("Unsupported PMO catalog")
    return Path(f"/Volumes/{catalog}/bronze/bronze_volume/pmo_app")


def load_contract(path: Path) -> dict[str, list[Column]]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("version") != 1 or set(content.get("tables", {})) != set(TABLES):
        raise ValueError("Unexpected PMO application table contract")
    return {table: [Column(**entry) for entry in content["tables"][table]] for table in TABLES}


def validate_columns(table: str, columns: Sequence[Column], contract: Sequence[Column]) -> None:
    actual = {target_column_name(table, column.name): column.sql_type for column in columns}
    expected = {column.name: column.sql_type for column in contract}
    if len(actual) != len(columns) or actual != expected:
        raise ValueError(f"Source columns/types do not match the application contract: {table}")


def pristine_bootstrap_id(users: list[dict], source_users: list[dict], initial_admin: str, other_target_rows: int) -> str | None:
    if len(users) != 1 or other_target_rows:
        return None
    user = users[0]
    matching_source = [row for row in source_users if (row.get("email") or "").lower() == initial_admin]
    if len(matching_source) != 1 or matching_source[0].get("global_role") != "ADMIN" or matching_source[0].get("is_active") is not True:
        return None
    if user.get("id") == matching_source[0].get("id"):
        return None
    expected = {"email": initial_admin, "name": initial_admin, "global_role": "ADMIN", "permissions": "[]", "is_active": True,
                "image": None, "last_login_at": None, "email_verified": None}
    if any(user.get(field) != value for field, value in expected.items()):
        return None
    if user.get("created_at") is None or user.get("created_at") != user.get("updated_at"):
        return None
    return user["id"]


def validate_records(records: dict[str, list[dict[str, object]]]) -> dict:
    if set(records) != set(TABLES):
        raise ValueError("Snapshot must contain all 18 PMO tables")
    identities = {}
    for table in TABLES:
        values = [row.get("id") for row in records[table]]
        if any(not isinstance(value, str) or not value.strip() for value in values) or len(set(values)) != len(values):
            raise ValueError(f"Missing or duplicate IDs: {table}")
        identities[table] = set(values)
    for table, field, parent in FOREIGN_KEYS:
        missing = sum(row.get(field) is not None and row[field] not in identities[parent] for row in records[table])
        if missing:
            raise ValueError(f"Broken source relationship {table}.{field}: {missing} rows")
    historical = {}
    for table, field, parent in (
        ("audit_logs", "user_id", "users"), ("audit_logs", "project_id", "projects"),
        ("project_snapshots", "project_id", "projects"), ("project_snapshots", "created_by_id", "users"),
        ("projects", "last_updated_by_id", "users"), ("gate_records", "updated_by_id", "users"),
    ):
        historical[f"{table}.{field}"] = sum(row.get(field) is not None and row[field] not in identities[parent] for row in records[table])
    emails = set()
    roles = {}
    active_users = 0
    for user in records["users"]:
        role = user.get("global_role")
        if role not in {"ADMIN", "EXECUTIVE", "MEMBER"} or type(user.get("is_active")) is not bool:
            raise ValueError("Invalid source user authorization")
        roles[role] = roles.get(role, 0) + 1
        active_users += int(user["is_active"])
        permissions = json.loads(user.get("permissions") or "[]")
        if not isinstance(permissions, list) or any(permission not in PERMISSIONS for permission in permissions):
            raise ValueError("Unknown source user permissions")
        email = user.get("email")
        if email is not None:
            if not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@etexgroup\.com", email.lower().strip()):
                raise ValueError("Source contains a non-Etex login identity")
            normalized = email.lower().strip()
            if normalized in emails:
                raise ValueError("Source contains duplicate login identities")
            emails.add(normalized)
    return {"roles": roles, "active_users": active_users, "historical_missing_references": historical}


def package_zip(folder: Path, destination: Path) -> str:
    files = [folder / "manifest.json", *[folder / f"PMO_{table}.csv" for table in TABLES]]
    if sum(path.stat().st_size for path in files) > MAX_PACKAGE_BYTES:
        raise ValueError("Snapshot exceeds the reviewed one-time migration size limit")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    with destination.open("xb") as handle:
        handle.write(output.getvalue())
    return sha256_file(destination)


def load_snapshot(base: Path, snapshot: str, contract: dict[str, list[Column]]) -> tuple[dict, dict, str]:
    name = snapshot_name(snapshot)
    archive_path = base / f"PMO_{name}.zip"
    expected_files = {"manifest.json", *[f"PMO_{table}.csv" for table in TABLES]}
    if archive_path.is_file():
        if archive_path.stat().st_size > MAX_PACKAGE_BYTES:
            raise ValueError("ZIP is larger than the migration size limit")
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) != len(expected_files) or {entry.filename for entry in entries} != expected_files:
                raise ValueError("ZIP must contain exactly the manifest and 18 CSV files at its root")
            if any(entry.file_size > MAX_FILE_BYTES for entry in entries) or sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES:
                raise ValueError("Expanded snapshot exceeds the migration size limit")
            contents = {entry.filename: archive.read(entry) for entry in entries}
    else:
        folder = base / name
        if {path.name for path in folder.iterdir()} != expected_files:
            raise ValueError("Snapshot folder must contain exactly the manifest and 18 CSV files")
        if any((folder / file).is_symlink() for file in expected_files):
            raise ValueError("Snapshot files cannot be symlinks")
        if any((folder / file).stat().st_size > MAX_FILE_BYTES for file in expected_files) or sum((folder / file).stat().st_size for file in expected_files) > MAX_PACKAGE_BYTES:
            raise ValueError("Snapshot exceeds the migration size limit")
        contents = {file: (folder / file).read_bytes() for file in expected_files}
    manifest_bytes = contents["manifest.json"]
    if len(manifest_bytes) > 1024 * 1024:
        raise ValueError("Manifest is too large")
    manifest = json.loads(manifest_bytes)
    if manifest.get("format") != FORMAT or manifest.get("snapshot") != name or manifest.get("source") != "engineering_global_pmo_s.pmo":
        raise ValueError("Unexpected PMO snapshot format or source")
    metadata = manifest.get("tables", [])
    if len(metadata) != len(TABLES) or {entry.get("table") for entry in metadata} != set(TABLES):
        raise ValueError("Manifest must declare all 18 PMO tables exactly once")
    records = {}
    csv.field_size_limit(16 * 1024 * 1024)
    for entry in metadata:
        table = entry["table"]
        filename = f"PMO_{table}.csv"
        if entry.get("file") != filename or type(entry.get("source_version")) is not int or entry["source_version"] < 0:
            raise ValueError(f"Invalid table metadata: {table}")
        payload = contents[filename]
        if entry.get("bytes") != len(payload) or entry.get("sha256") != hashlib.sha256(payload).hexdigest():
            raise ValueError(f"CSV checksum or byte count mismatch: {table}")
        columns = [Column(**column) for column in entry["columns"]]
        validate_columns(table, columns, contract[table])
        reader = csv.reader(io.StringIO(payload.decode("utf-8"), newline=""), strict=True)
        if next(reader, None) != [column.name for column in columns]:
            raise ValueError(f"CSV header mismatch: {table}")
        rows = []
        for values in reader:
            if len(values) != len(columns):
                raise ValueError(f"CSV column count mismatch: {table}")
            rows.append({column.name: decode_cell(value, column) for value, column in zip(values, columns)})
        if type(entry.get("rows")) is not int or entry["rows"] != len(rows):
            raise ValueError(f"CSV row count mismatch: {table}")
        records[table] = rows
    summary = validate_records(records)
    if manifest.get("authorization_summary") != summary:
        raise ValueError("Snapshot authorization/relationship summary does not match its contents")
    return manifest, records, hashlib.sha256(manifest_bytes).hexdigest()