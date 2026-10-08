"""Single-run EIC and Salesforce refresh for the OG data product."""

import csv
import json
import os
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from og_matching import databricks_llm_decider, match_projects
from og_screening import build_screen_delta, plan_screening, priority_candidate_pairs


SECTORS = {"Upstream": 1, "Midstream": 7, "Downstream": 2}
OUTPUT_DIR = Path("/Workspace/Users/mustafaarda.bicakci@etexgroup.com/Initiatives/2492_OG_Market_Intelligence/match_outputs")
SALESFORCE_QUERY = """
SELECT BK_Opportunity_Id AS opportunity_id,
       Name AS opportunity_name,
       Etex_Parent_Project AS parent_project_id,
       Etex_Country AS country,
       Etex_Region AS region,
       Account_Id AS account_id,
       accounts.account_name,
    YEAR(Etex_Estimated_First_Delivery_Date) AS estimated_first_delivery_year,
    YEAR(Etex_Phase_Date) AS phase_year,
    Last_Modified_Date AS source_last_modified_at,
       Stage_Name AS stage,
       Etex_Project_Type AS project_type,
       Etex_Project_Subtype AS project_subtype
FROM `synapse-prd`.dwh.f_comm_opportunity opportunities
LEFT JOIN (
    SELECT BK_ACCOUNT_ID, MAX(ACCOUNT_NAME) AS account_name
    FROM `synapse-prd`.dwh.d_comm_account
    GROUP BY BK_ACCOUNT_ID
) accounts ON opportunities.Account_Id = accounts.BK_ACCOUNT_ID
WHERE Etex_Project_Subtype IN ('Oil&Gas', 'Gas')
"""


def fetch_inventory(eic_post):
    projects_by_id = {}
    for sector_name, sector_id in SECTORS.items():
        projects = eic_post("/v1/projects/search", {
            "energySector": sector_id,
            "includeOperators": True,
            "includeContracts": True,
            "includeFid": True,
            "includeAllLocations": True,
        })
        names = eic_post("/v1/projectnames/search", {"energySector": sector_id})
        if not isinstance(projects, list) or not isinstance(names, list):
            raise ValueError(f"EIC {sector_name} must return complete project and name lists")
        project_ids = [project.get("projectId") for project in projects]
        name_ids = [project.get("projectId") for project in names]
        if (not project_ids or None in project_ids or None in name_ids
                or len(project_ids) != len(set(project_ids))
                or len(name_ids) != len(set(name_ids))
                or set(project_ids) != set(name_ids)):
            raise ValueError(f"EIC {sector_name} project IDs do not match its name index")

        for project in projects:
            project_id = project["projectId"]
            if project_id not in projects_by_id:
                locations = project.get("locations") or []
                main_location = next((location for location in locations if location.get("main")),
                                     locations[0] if locations else {})
                projects_by_id[project_id] = {
                    "project_id": int(project_id),
                    "project_name": str(project.get("projectName") or ""),
                    "country": str(main_location.get("country") or ""),
                    "locality": str(main_location.get("locality") or ""),
                    "operator_name": next((str(company.get("companyName") or "")
                                           for company in (project.get("operatingCompanies") or [])
                                           if company.get("isOperator") and company.get("companyName")),
                                          str(project.get("operator") or "")),
                    "stage": str(project.get("projectStage") or ""),
                    "status": str(project.get("projectStatus") or ""),
                    "startup_year": (int(project["startupYear"])
                                     if project.get("startupYear") is not None else None),
                    "sectors": [sector_name],
                }
            elif sector_name not in projects_by_id[project_id]["sectors"]:
                projects_by_id[project_id]["sectors"].append(sector_name)

    return [{**project, "sectors": ", ".join(project["sectors"])}
            for project in projects_by_id.values()]


def load_previous_matches(spark):
    from pyspark.sql import functions as F

    schema = "automation_s.og"
    if not spark.catalog.tableExists(f"{schema}.completed_runs"):
        return []
    completed = (spark.table(f"{schema}.completed_runs")
                 .select("run_utc", "eic_projects")
                 .orderBy(F.col("run_utc").desc()).limit(1).collect())
    if not completed:
        return []
    if not spark.catalog.tableExists(f"{schema}.match_review_snapshots"):
        raise ValueError("Completed run has no match snapshots")
    rows = [row.asDict(recursive=True) for row in spark.table(f"{schema}.match_review_snapshots")
            .where(F.col("run_utc") == completed[0]["run_utc"]).collect()]
    if len(rows) != completed[0]["eic_projects"] or len({row["project_id"] for row in rows}) != len(rows):
        raise ValueError("Completed run has incomplete or duplicate match snapshots")
    return rows


def load_screening_history(spark):
    from pyspark.sql import functions as F

    schema = "automation_s.og"
    if not (spark.catalog.tableExists(f"{schema}.completed_runs")
            and spark.catalog.tableExists(f"{schema}.pair_screen_snapshots")):
        return [], [], None
    completed = (spark.table(f"{schema}.completed_runs")
                 .orderBy(F.col("run_utc").desc()).limit(1).collect())
    if not completed or "screening_version" not in completed[0].asDict():
        return [], [], None
    last_run = completed[0]
    if not last_run["screening_version"]:
        return [], [], None
    projects = [row.asDict(recursive=True) for row in spark.table(f"{schema}.eic_project_snapshots")
                .where(F.col("run_utc") == last_run["run_utc"]).collect()]
    opportunities = [row.asDict(recursive=True) for row in spark.table(f"{schema}.salesforce_opportunity_snapshots")
                     .where(F.col("run_utc") == last_run["run_utc"]).collect()]
    if (len(projects) != last_run["eic_projects"] or len(opportunities) != last_run["salesforce_opportunities"]
            or len({row["project_id"] for row in projects}) != len(projects)
            or len({row["opportunity_id"] for row in opportunities}) != len(opportunities)):
        raise ValueError("Previous completed source inventories are incomplete or duplicated")
    return projects, opportunities, last_run["screening_version"]


def run_pipeline(spark, dbutils, *, workspace_client=None, eic_post=None,
                 output_dir=OUTPUT_DIR, max_llm_calls=100):
    from databricks.sdk import WorkspaceClient
    from pyspark.sql.types import (ArrayType, BooleanType, DoubleType, IntegerType,
                                   StringType, StructField, StructType)

    from og_data_product import publish_snapshot

    if eic_post is None:
        import requests

        api_key = dbutils.secrets.get(scope="WE-SPOKE-MDP-AUT-T-KV", key="EIC-API")
        tls_verify = os.environ.get("EIC_CA_BUNDLE") or False
        if tls_verify is False:
            warnings.warn("EIC TLS verification is disabled for this POC; configure EIC_CA_BUNDLE", RuntimeWarning)
        session = requests.Session()

        def eic_post(endpoint, body):
            response = session.post(
                f"https://memberapi.the-eic.com{endpoint}",
                headers={"Authorization": f"key {api_key}", "Accept": "application/json"},
                json=body, timeout=60, verify=tls_verify,
            )
            response.raise_for_status()
            return response.json()

    projects = fetch_inventory(eic_post)
    project_schema = StructType([
        StructField("project_id", IntegerType(), False),
        StructField("project_name", StringType(), True),
        StructField("country", StringType(), True),
        StructField("locality", StringType(), True),
        StructField("operator_name", StringType(), True),
        StructField("stage", StringType(), True),
        StructField("status", StringType(), True),
        StructField("startup_year", IntegerType(), True),
        StructField("sectors", StringType(), True),
    ])
    df_projects = spark.createDataFrame(projects, schema=project_schema)
    df_opportunities = spark.sql(SALESFORCE_QUERY)
    opportunities = [row.asDict(recursive=True) for row in df_opportunities.collect()]
    opportunity_ids = [row["opportunity_id"] for row in opportunities]
    if None in opportunity_ids or len(opportunity_ids) != len(set(opportunity_ids)):
        raise ValueError("Salesforce opportunities need distinct non-null IDs")
    subtype_counts = dict(Counter(row["project_subtype"] for row in opportunities))
    if set(subtype_counts) != {"Oil&Gas", "Gas"}:
        raise ValueError(f"Expected both Salesforce subtypes, got {subtype_counts}")

    if workspace_client is None:
        workspace_client = WorkspaceClient()
    prior_projects, prior_opportunities, prior_version = load_screening_history(spark)
    screen_plan = plan_screening(projects, opportunities, prior_projects, prior_opportunities, prior_version)
    previous_matches = load_previous_matches(spark)
    priority_pairs = priority_candidate_pairs(
        match_projects(projects, opportunities, llm_decider=None)[0], screen_plan)
    match_rows, match_summary = match_projects(
        projects, opportunities,
        llm_decider=databricks_llm_decider(workspace_client),
        max_llm_calls=max_llm_calls,
        previous_matches=previous_matches,
        priority_pairs=priority_pairs,
    )
    if len(match_rows) != len(projects):
        raise ValueError("Every EIC project needs one review record")
    df_screen = build_screen_delta(spark, projects, opportunities, match_rows, screen_plan)
    match_schema = StructType([
        StructField("project_id", IntegerType(), False),
        StructField("project_name", StringType(), True),
        StructField("country", StringType(), True),
        StructField("sectors", StringType(), True),
        StructField("opportunity_id", StringType(), True),
        StructField("opportunity_name", StringType(), True),
        StructField("opportunity_subtype", StringType(), True),
        StructField("candidate_ids", ArrayType(StringType()), True),
        StructField("candidate_names", ArrayType(StringType()), True),
        StructField("candidate_countries", ArrayType(StringType()), True),
        StructField("candidate_subtypes", ArrayType(StringType()), True),
        StructField("candidate_scores", ArrayType(DoubleType()), True),
        StructField("best_candidate_score", DoubleType(), True),
        StructField("match_status", StringType(), False),
        StructField("review_required", BooleanType(), False),
        StructField("decision_source", StringType(), False),
        StructField("reason", StringType(), False),
        StructField("input_fingerprint", StringType(), False),
        StructField("pair_reviews", StringType(), False),
        StructField("legacy_pair_reviews", StringType(), False),
        StructField("llm_evidence", StringType(), True),
    ])
    df_matches = spark.createDataFrame(match_rows, schema=match_schema)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    review_file = output_dir / f"eic_sf_review_{run_id}.csv"
    summary_file = output_dir / f"eic_sf_summary_{run_id}.json"
    if review_file.exists() or summary_file.exists():
        raise FileExistsError(f"Audit output for {run_id} already exists")

    def csv_value(value):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value if value is not None else "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    with review_file.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(match_rows[0]))
        writer.writeheader()
        for row in match_rows:
            writer.writerow({key: csv_value(value) for key, value in row.items()})

    summary = {
        **match_summary,
        "possible_pairs": screen_plan["possible_pairs"],
        "screened_pairs": screen_plan["screened_pairs"],
        "new_eic_projects": screen_plan["new_eic_projects"],
        "modified_eic_projects": screen_plan["modified_eic_projects"],
        "new_salesforce_opportunities": screen_plan["new_salesforce_opportunities"],
        "modified_salesforce_opportunities": screen_plan["modified_salesforce_opportunities"],
        "changed_eic_projects": len(screen_plan["source_changed_projects"]),
        "changed_salesforce_opportunities": len(screen_plan["source_changed_opportunities"]),
        "priority_candidate_pairs": len(priority_pairs),
        "run_utc": run_id,
        "model_endpoint": "databricks-gpt-5-4-mini",
        "salesforce_subtypes": subtype_counts,
        "input_opportunities": len(opportunities),
        "policy": "LLM proposals require human review; New is not proof of absence",
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    publish_snapshot(spark, run_id, df_projects, df_opportunities, df_matches,
                     match_summary, subtype_counts, df_screen, screen_plan)
    return summary