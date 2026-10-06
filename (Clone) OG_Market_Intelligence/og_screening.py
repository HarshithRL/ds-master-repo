"""Plan auditable, two-sided incremental screening of source inventories."""

from og_matching import country_key, fingerprint, informative_tokens, normalize


SCREENING_VERSION = "6"


PROJECT_FIELDS = ("project_name", "country", "locality", "operator_name", "startup_year", "stage")
OPPORTUNITY_FIELDS = ("opportunity_name", "country", "region", "account_name", "stage", "project_subtype",
                      "estimated_first_delivery_year", "phase_year")
PROJECT_OBSERVED_FIELDS = ("project_name", "country", "locality", "operator_name", "sectors", "stage",
                           "status", "startup_year")
OPPORTUNITY_OBSERVED_FIELDS = ("opportunity_name", "country", "region", "parent_project_id", "account_id",
                               "account_name", "stage", "project_type", "project_subtype",
                               "estimated_first_delivery_year", "phase_year", "source_last_modified_at")


def source_fingerprint(row, fields):
    return fingerprint({"version": SCREENING_VERSION, **{field: row.get(field) for field in fields}})


def observed_fingerprint(row, fields):
    return fingerprint({field: row.get(field) for field in fields})


def plan_screening(projects, opportunities, previous_projects=(), previous_opportunities=(),
                   previous_version=None):
    old_projects = {int(row["project_id"]): source_fingerprint(row, PROJECT_FIELDS)
                    for row in previous_projects}
    old_opportunities = {str(row["opportunity_id"]): source_fingerprint(row, OPPORTUNITY_FIELDS)
                         for row in previous_opportunities}
    observed_projects = {int(row["project_id"]): observed_fingerprint(row, PROJECT_OBSERVED_FIELDS)
                         for row in previous_projects}
    observed_opportunities = {str(row["opportunity_id"]): observed_fingerprint(row, OPPORTUNITY_OBSERVED_FIELDS)
                              for row in previous_opportunities}
    first_pass = previous_version != SCREENING_VERSION
    source_changed_projects = [row for row in projects if old_projects.get(int(row["project_id"]))
                               != source_fingerprint(row, PROJECT_FIELDS)]
    source_changed_opportunities = [row for row in opportunities if
                                    old_opportunities.get(str(row["opportunity_id"]))
                                    != source_fingerprint(row, OPPORTUNITY_FIELDS)]
    changed_projects = projects if first_pass else source_changed_projects
    unchanged_projects = [] if first_pass else [row for row in projects if
                                               old_projects.get(int(row["project_id"]))
                                               == source_fingerprint(row, PROJECT_FIELDS)]
    changed_opportunities = opportunities if first_pass else source_changed_opportunities
    modified_projects = sum(
        int(row["project_id"]) in observed_projects
        and observed_projects[int(row["project_id"])] != observed_fingerprint(row, PROJECT_OBSERVED_FIELDS)
        for row in projects
    )
    modified_opportunities = sum(
        str(row["opportunity_id"]) in observed_opportunities
        and observed_opportunities[str(row["opportunity_id"])]
        != observed_fingerprint(row, OPPORTUNITY_OBSERVED_FIELDS)
        for row in opportunities
    )
    return {
        "changed_projects": changed_projects,
        "unchanged_projects": unchanged_projects,
        "changed_opportunities": changed_opportunities,
        "source_changed_projects": source_changed_projects,
        "source_changed_opportunities": source_changed_opportunities,
        "new_eic_projects": sum(int(row["project_id"]) not in old_projects for row in projects),
        "modified_eic_projects": modified_projects,
        "new_salesforce_opportunities": sum(str(row["opportunity_id"]) not in old_opportunities
                                            for row in opportunities),
        "modified_salesforce_opportunities": modified_opportunities,
        "screened_pairs": len(changed_projects) * len(opportunities)
                          + len(unchanged_projects) * len(changed_opportunities),
        "possible_pairs": len(projects) * len(opportunities),
    }


def priority_candidate_pairs(matches, plan):
    changed_project_ids = {int(row["project_id"]) for row in plan["source_changed_projects"]}
    changed_opportunity_ids = {str(row["opportunity_id"]) for row in plan["source_changed_opportunities"]}
    return {(int(row["project_id"]), str(opportunity_id))
            for row in matches for opportunity_id in row["candidate_ids"]
            if int(row["project_id"]) in changed_project_ids
            or str(opportunity_id) in changed_opportunity_ids}


def build_screen_delta(spark, projects, opportunities, matches, plan):
    from pyspark.sql import functions as F
    from pyspark.sql.types import (ArrayType, DoubleType, IntegerType, StringType,
                                   StructField, StructType)

    project_schema = StructType([
        StructField("project_id", IntegerType(), False),
        StructField("eic_name", StringType(), True),
        StructField("eic_country", StringType(), True),
        StructField("eic_tokens", ArrayType(StringType()), True),
        StructField("project_fingerprint", StringType(), False),
    ])
    opportunity_schema = StructType([
        StructField("opportunity_id", StringType(), False),
        StructField("sf_name", StringType(), True),
        StructField("sf_country", StringType(), True),
        StructField("sf_tokens", ArrayType(StringType()), True),
        StructField("opportunity_fingerprint", StringType(), False),
    ])
    candidate_schema = StructType([
        StructField("project_id", IntegerType(), False),
        StructField("candidate_ids", ArrayType(StringType()), True),
        StructField("candidate_scores", ArrayType(DoubleType()), True),
    ])

    def project_frame(rows):
        return spark.createDataFrame([(
            int(row["project_id"]), normalize(row.get("project_name")), country_key(row.get("country")),
            sorted(informative_tokens(row.get("project_name"))), source_fingerprint(row, PROJECT_FIELDS),
        ) for row in rows], project_schema)

    def opportunity_frame(rows):
        return spark.createDataFrame([(
            str(row["opportunity_id"]), normalize(row.get("opportunity_name")), country_key(row.get("country")),
            sorted(informative_tokens(row.get("opportunity_name"))), source_fingerprint(row, OPPORTUNITY_FIELDS),
        ) for row in rows], opportunity_schema)

    candidate_frame = spark.createDataFrame([(
        int(row["project_id"]), row["candidate_ids"], row["candidate_scores"],
    ) for row in matches], candidate_schema)
    all_opportunities = opportunity_frame(opportunities)
    changed_projects = project_frame(plan["changed_projects"])
    unchanged_projects = project_frame(plan["unchanged_projects"])
    changed_opportunities = opportunity_frame(plan["changed_opportunities"])
    pairs = (changed_projects.crossJoin(F.broadcast(all_opportunities))
             .unionByName(unchanged_projects.crossJoin(F.broadcast(changed_opportunities))))
    pairs = pairs.join(F.broadcast(candidate_frame), "project_id")
    shared = F.size(F.array_intersect(F.col("eic_tokens"), F.col("sf_tokens")))
    candidate = F.array_contains(F.col("candidate_ids"), F.col("opportunity_id"))
    reason = (F.when(candidate, "candidate")
              .when((F.col("eic_country") != "") & (F.col("sf_country") != "")
                    & (F.col("eic_country") != F.col("sf_country")), "country_conflict")
              .when(shared == 0, "no_name_overlap")
              .when((shared < 2) & (F.col("eic_name") != F.col("sf_name")), "weak_name_overlap")
              .otherwise("low_name_score"))
    return pairs.select(
        "project_id", "opportunity_id", "project_fingerprint", "opportunity_fingerprint",
        reason.alias("screen_reason"),
        F.when(candidate, F.expr("element_at(candidate_scores, CAST(array_position(candidate_ids, opportunity_id) AS INT))"))
         .otherwise(F.lit(None).cast("double")).alias("candidate_score"),
    )