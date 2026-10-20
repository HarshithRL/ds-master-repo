import re


BUNDLE_NAME = "ursa-kpi-dashboards"
TABLE_PREFIX = "URSA_KPI_"
LAYERS = ("bronze", "silver", "gold")
ENVIRONMENTS = {
    "D": ("automation_d", "7181820732839861"),
    "T": ("automation_d", "7181820732839861"),
    "A": ("automation_a", "4796304964978539"),
    "P": ("automation_p", "4844910598668398"),
}


def validate_environment(target, catalog, source_catalog, workspace_id):
    expected = ENVIRONMENTS.get(target)
    if expected is None or expected != (catalog, str(workspace_id)):
        raise ValueError("Target, automation catalog and actual workspace must agree")
    if source_catalog != "synapse-prd":
        raise ValueError("Only the declared read-only Synapse source is supported")


def table_name(component, target):
    if target not in ENVIRONMENTS or not re.fullmatch(r"[a-z][a-z0-9_]*", component):
        raise ValueError("Invalid bundle-owned table identity")
    return TABLE_PREFIX + component + ("_dev" if target == "D" else "")


def relation(catalog, layer, component, target):
    if target not in ENVIRONMENTS or catalog != ENVIRONMENTS[target][0] or layer not in LAYERS:
        raise ValueError("Only the target's existing bronze, silver and gold schemas are allowed")
    return f"`{catalog}`.`{layer}`.`{table_name(component, target)}`"


def quote_column(name):
    if not isinstance(name, str) or not name or "`" in name or "\x00" in name:
        raise ValueError("Invalid projected column name")
    return "`" + name + "`"