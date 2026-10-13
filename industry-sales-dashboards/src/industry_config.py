import re


MAPPING_COLUMNS = ("sales_org_code", "sales_organization", "cs_team")
WORKSPACE_CATALOGS = {
    "7181820732839861": "automation_d",
    "4796304964978539": "automation_a",
    "4844910598668398": "automation_p",
}
TARGET_CATALOGS = {
    "D": "automation_d",
    "T": "automation_d",
    "A": "automation_a",
    "P": "automation_p",
}


def validate_table_name(table_name, target):
    if not re.fullmatch(r"industry_sales_cs_team_sales_org_mapping(?:_dev)?", table_name):
        raise ValueError(f"Invalid mapping table name: {table_name!r}")
    if table_name.endswith("_dev") != (target == "D"):
        raise ValueError(f"Target {target!r} cannot use mapping table {table_name!r}")


def validate_environment(catalog, source_catalog, target, workspace_id):
    if TARGET_CATALOGS.get(target) != catalog:
        raise ValueError(f"Target {target!r} cannot write catalog {catalog!r}")
    if WORKSPACE_CATALOGS.get(str(workspace_id)) != catalog:
        raise ValueError(f"Workspace {workspace_id!r} cannot write catalog {catalog!r}")
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", source_catalog):
        raise ValueError(f"Invalid source catalog: {source_catalog!r}")


def validate_mapping(rows):
    if not rows:
        raise ValueError("The mapping seed must not be empty")
    codes = set()
    for row in rows:
        if set(row) != set(MAPPING_COLUMNS):
            raise ValueError(f"Unexpected mapping columns: {sorted(row)}")
        if any(not isinstance(row[column], str) or not row[column].strip() for column in MAPPING_COLUMNS):
            raise ValueError("Mapping fields must be nonempty strings")
        if row["sales_org_code"] in codes:
            raise ValueError(f"Duplicate sales organization: {row['sales_org_code']}")
        codes.add(row["sales_org_code"])
    return rows