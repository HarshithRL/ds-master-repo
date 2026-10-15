import json
import re
from pathlib import Path

from dataset_results import result_storage_name, unique_result_producers
from industry_config import MAPPING_TABLE_NAME, RESULT_STATE_TABLE_NAME


CONFIG = Path(__file__).parent / "config/dashboard_readers.json"


def reader_config():
    config = json.loads(CONFIG.read_text())
    if set(config["dashboards"]) != {"open_orders", "quotations"}:
        raise ValueError("Both dashboard reader lists are required")
    for key, tier in (("open_orders", "READ"), ("quotations", "WRITE")):
        dashboard = config["dashboards"][key]
        if dashboard["tier"] != tier or dashboard["group_name"] != "AUTOMATION.INDUSTRYSALESDASHBOARDS.CONSUMER." + tier:
            raise ValueError("Unsupported reader group identity")
        members = dashboard["members"]
        if len(members) != len(set(members)) or any(not re.fullmatch(r"[a-z0-9._-]+@etexgroup\.com", member) for member in members + config["common_members"]):
            raise ValueError("Reader addresses must be unique normalized Etex addresses")
    return config


def dashboard_members(key):
    config = reader_config()
    return sorted(set(config["common_members"] + config["dashboards"][key]["members"]))


def dashboard_relations(plans, key):
    relations = {("gold", RESULT_STATE_TABLE_NAME)}
    relations.update((layer, MAPPING_TABLE_NAME) for layer in ("bronze", "silver", "gold"))
    for table in unique_result_producers([plan for plan in plans if plan["dashboard"] == key]):
        relations.add(("gold", table))
        relations.add(("silver", result_storage_name(table)))
    return relations


def consumer_reader_groups(plans):
    config = reader_config()
    groups = []
    for key in ("open_orders", "quotations"):
        grants = [{"catalog": "automation", "privileges": ["USE_CATALOG"]}]
        grants.extend({"catalog": "automation", "schema": layer, "privileges": ["USE_SCHEMA"]} for layer in ("bronze", "silver", "gold"))
        grants.extend({"catalog": "automation", "schema": layer, "table": table, "privileges": ["SELECT"]} for layer, table in sorted(dashboard_relations(plans, key)))
        groups.append({"tier": config["dashboards"][key]["tier"], "grants": grants, "members": dashboard_members(key)})
    return groups