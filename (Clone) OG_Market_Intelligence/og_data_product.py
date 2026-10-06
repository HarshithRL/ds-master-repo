"""Publish completed OG snapshots for Databricks SQL consumers."""

from pyspark.sql import functions as F
from og_screening import OPPORTUNITY_OBSERVED_FIELDS, PROJECT_OBSERVED_FIELDS, SCREENING_VERSION


SCHEMA = "automation_s.og"


def publish_snapshot(spark, run_id, eic_projects, salesforce_opportunities, matches,
                     match_summary, subtype_counts, screen_frame=None, screen_plan=None):
    expected_projects = match_summary["total_projects"]
    if (eic_projects.count() != expected_projects or matches.count() != expected_projects
            or eic_projects.select("project_id").distinct().count() != expected_projects
            or matches.select("project_id").distinct().count() != expected_projects
            or eic_projects.select("project_id").subtract(matches.select("project_id")).count()):
        raise ValueError("EIC and review rows must contain the same distinct project IDs")
    actual_subtypes = {row["project_subtype"]: row["count"] for row in
                       salesforce_opportunities.groupBy("project_subtype").count().collect()}
    if actual_subtypes != subtype_counts or set(actual_subtypes) != {"Oil&Gas", "Gas"}:
        raise ValueError("Salesforce snapshot must contain the verified Oil&Gas and Gas rows")
    if screen_frame is not None and (screen_plan is None or screen_frame.count() != screen_plan["screened_pairs"]
                                     or screen_frame.select("project_id", "opportunity_id").distinct().count()
                                     != screen_plan["screened_pairs"]
                                     or screen_plan["possible_pairs"] != expected_projects
                                     * salesforce_opportunities.count()):
        raise ValueError("Pair screening must cover exactly the planned changed-source cross-products")

    snapshot_names = ("eic_project_snapshots", "salesforce_opportunity_snapshots",
                      "match_review_snapshots", "pair_screen_snapshots")
    existing = {name for name in ("completed_runs", *snapshot_names,
                                   "eic_projects_current", "salesforce_opportunities_current",
                                   "match_review_current", "project_overview_current", "pair_review_current",
                                   "pair_screen_current", "pair_labels")
                if spark.catalog.tableExists(f"{SCHEMA}.{name}")}
    if existing and "completed_runs" not in existing:
        raise ValueError(f"OG schema already has conflicting objects: {sorted(existing)}")
    if "pair_screen_snapshots" in existing and screen_frame is None:
        raise ValueError("Publishing without full pair screening would invalidate the current coverage view")
    for name in existing.intersection({"completed_runs", *snapshot_names}):
        if spark.table(f"{SCHEMA}.{name}").where(F.col("run_utc") == run_id).limit(1).count():
            raise ValueError(f"Run {run_id} already has rows in {SCHEMA}.{name}")

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.completed_runs (
            run_utc STRING, completed_at_utc TIMESTAMP,
            eic_projects BIGINT, salesforce_opportunities BIGINT,
            oil_gas_opportunities BIGINT, gas_opportunities BIGINT,
            llm_calls BIGINT, matched BIGINT, partial BIGINT,
            uncertain BIGINT, new_candidates BIGINT
        ) USING DELTA
    """)

    snapshots = (
        ("eic_project_snapshots", eic_projects.select(
            "project_id", "project_name", "country", "locality", "operator_name",
            "sectors", "stage", "status", "startup_year")),
        ("salesforce_opportunity_snapshots", salesforce_opportunities.select(
            "opportunity_id", "opportunity_name", "country", "region", "parent_project_id",
            "account_id", "account_name", "stage", "project_type", "project_subtype",
            "estimated_first_delivery_year", "phase_year", "source_last_modified_at")),
        ("match_review_snapshots", matches),
    )
    for table_name, frame in snapshots:
        (frame.withColumn("run_utc", F.lit(run_id))
         .write.format("delta").mode("append")
         .option("mergeSchema", "true")
         .saveAsTable(f"{SCHEMA}.{table_name}"))
    if screen_frame is not None:
        (screen_frame.withColumn("run_utc", F.lit(run_id))
         .write.format("delta").mode("append").saveAsTable(f"{SCHEMA}.pair_screen_snapshots"))
        spark.sql(f"""
            CREATE OR REPLACE VIEW {SCHEMA}.pair_screen_current AS
            WITH ranked AS (
                SELECT screening.*,
                    ROW_NUMBER() OVER (PARTITION BY screening.project_id, screening.opportunity_id
                                       ORDER BY screening.run_utc DESC) AS position
                FROM {SCHEMA}.pair_screen_snapshots screening
                JOIN {SCHEMA}.completed_runs completed ON screening.run_utc = completed.run_utc
            ), latest AS (SELECT MAX(run_utc) AS run_utc FROM {SCHEMA}.completed_runs)
            SELECT ranked.project_id AS eic_project_id, ranked.opportunity_id AS salesforce_opportunity_id,
                ranked.project_fingerprint, ranked.opportunity_fingerprint,
                ranked.screen_reason, ranked.candidate_score, ranked.run_utc AS last_screened_run_utc
            FROM ranked
            CROSS JOIN latest
            JOIN {SCHEMA}.eic_project_snapshots eic
              ON eic.run_utc = latest.run_utc AND eic.project_id = ranked.project_id
            JOIN {SCHEMA}.salesforce_opportunity_snapshots sf
              ON sf.run_utc = latest.run_utc AND sf.opportunity_id = ranked.opportunity_id
            WHERE ranked.position = 1
        """)
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.pair_labels (
                eic_project_id INT, salesforce_opportunity_id STRING,
                is_match BOOLEAN, reviewer STRING, reviewed_at_utc TIMESTAMP, evidence STRING
            ) USING DELTA
        """)
        spark.sql(f"""
            CREATE OR REPLACE VIEW {SCHEMA}.pair_screen_quality_current AS
            WITH labelled AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY eic_project_id, salesforce_opportunity_id
                    ORDER BY reviewed_at_utc DESC
                ) AS position
                FROM {SCHEMA}.pair_labels
                WHERE reviewer IS NOT NULL AND is_match IS NOT NULL
            ), evaluated AS (
                SELECT labelled.is_match, screened.screen_reason
                FROM labelled
                JOIN {SCHEMA}.pair_screen_current screened
                  ON screened.eic_project_id = labelled.eic_project_id
                 AND screened.salesforce_opportunity_id = labelled.salesforce_opportunity_id
                WHERE labelled.position = 1
            )
            SELECT COUNT(*) AS labelled_pairs,
                COUNT_IF(is_match) AS labelled_positive_pairs,
                COUNT_IF(is_match AND screen_reason = 'candidate') AS retrieved_positive_pairs,
                CASE WHEN COUNT_IF(is_match) > 0 THEN
                    CAST(COUNT_IF(is_match AND screen_reason = 'candidate') AS DOUBLE) / COUNT_IF(is_match)
                ELSE NULL END AS labelled_retrieval_recall
            FROM evaluated
        """)

    for view_name, table_name, id_field, observed_fields in (
        ("eic_projects_current", "eic_project_snapshots", "project_id", PROJECT_OBSERVED_FIELDS),
        ("salesforce_opportunities_current", "salesforce_opportunity_snapshots", "opportunity_id",
         OPPORTUNITY_OBSERVED_FIELDS),
    ):
        source_fields = ", ".join(f"'{field}', snapshot.{field}" for field in observed_fields)
        spark.sql(f"""
            CREATE OR REPLACE VIEW {SCHEMA}.{view_name} AS
            WITH latest AS (SELECT MAX(run_utc) AS run_utc FROM {SCHEMA}.completed_runs),
            previous AS (
                SELECT MAX(run_utc) AS run_utc FROM {SCHEMA}.completed_runs
                WHERE run_utc < (SELECT run_utc FROM latest)
            ), observed AS (
                SELECT snapshot.{id_field}, snapshot.run_utc,
                    TO_JSON(NAMED_STRUCT({source_fields})) AS source_fields
                FROM {SCHEMA}.{table_name} snapshot
                JOIN {SCHEMA}.completed_runs completed ON snapshot.run_utc = completed.run_utc
            ), changes AS (
                SELECT observed.*,
                    LAG(source_fields) OVER (PARTITION BY {id_field} ORDER BY run_utc) AS prior_fields
                FROM observed
            ), history AS (
                SELECT {id_field}, MIN(run_utc) AS first_seen_run_utc,
                    MAX(CASE WHEN prior_fields IS NULL OR source_fields <> prior_fields
                        THEN run_utc END) AS last_observed_change_run_utc
                FROM changes GROUP BY {id_field}
            )
            SELECT snapshot.*, history.first_seen_run_utc, history.last_observed_change_run_utc,
                CASE WHEN previous.run_utc IS NULL THEN FALSE
                     ELSE prior.{id_field} IS NULL END AS new_since_previous_run,
                CASE WHEN previous.run_utc IS NULL OR prior.{id_field} IS NULL THEN FALSE
                     ELSE history.last_observed_change_run_utc = latest.run_utc
                END AS changed_since_previous_run
            FROM {SCHEMA}.{table_name} snapshot
            CROSS JOIN latest
            CROSS JOIN previous
            JOIN history ON snapshot.{id_field} = history.{id_field}
            LEFT JOIN {SCHEMA}.{table_name} prior
              ON prior.run_utc = previous.run_utc AND prior.{id_field} = snapshot.{id_field}
            WHERE snapshot.run_utc = latest.run_utc
        """)
    spark.sql(f"""
        CREATE OR REPLACE VIEW {SCHEMA}.match_review_current AS
        SELECT project_id, project_name, country, sectors,
            opportunity_id, opportunity_name, opportunity_subtype,
            candidate_ids, candidate_names, candidate_countries, candidate_subtypes,
            candidate_scores, best_candidate_score, match_status, review_required,
            decision_source, reason, llm_evidence, run_utc
        FROM {SCHEMA}.match_review_snapshots
        WHERE run_utc = (SELECT MAX(run_utc) FROM {SCHEMA}.completed_runs)
    """)
    spark.sql(f"""
        CREATE OR REPLACE VIEW {SCHEMA}.pair_review_current AS
        SELECT review.run_utc, review.project_id AS eic_project_id,
            review.project_name AS eic_project_name, review.country AS eic_country,
            eic.startup_year AS eic_startup_year, eic.status AS eic_status,
            eic.stage AS eic_stage,
            sf.opportunity_id AS salesforce_opportunity_id,
            sf.opportunity_name AS salesforce_opportunity_name,
            sf.country AS salesforce_country, sf.project_subtype AS salesforce_subtype,
            sf.stage AS salesforce_stage,
            sf.estimated_first_delivery_year AS salesforce_estimated_first_delivery_year,
            sf.phase_year AS salesforce_phase_year,
            sf.source_last_modified_at AS salesforce_last_modified_at,
            element_at(review.candidate_scores, candidate_position + 1) AS candidate_score,
            CASE WHEN review.decision_source = 'exact_name_country'
                 AND review.opportunity_id = candidate_id THEN 'exact'
                 WHEN review.decision_source = 'exact_name_country'
                     THEN 'not_reviewed_exact_project'
                 ELSE coalesce(review.current_decision.decision, 'pending') END AS pair_decision,
            review.current_decision.rationale AS llm_evidence,
            review.prior_decision.decision AS prior_llm_decision,
            review.prior_decision.rationale AS prior_llm_evidence,
              review.match_status,
              CASE WHEN review.decision_source = 'exact_name_country'
                  AND review.opportunity_id = candidate_id THEN FALSE
                  ELSE TRUE END AS review_required,
              review.reason
                FROM (
                        SELECT source.*, candidate_position, candidate_id,
                            element_at(from_json(source.pair_reviews,
                                'MAP<STRING,STRUCT<project_fingerprint:STRING,candidate_fingerprint:STRING,decision:STRING,rationale:STRING>>'),
                                candidate_id) AS current_decision,
                            element_at(from_json(source.legacy_pair_reviews,
                                'MAP<STRING,STRUCT<project_fingerprint:STRING,candidate_fingerprint:STRING,decision:STRING,rationale:STRING>>'),
                                candidate_id) AS prior_decision
                        FROM {SCHEMA}.match_review_snapshots source
                        LATERAL VIEW posexplode(source.candidate_ids) shortlisted AS candidate_position, candidate_id
                        WHERE source.run_utc = (SELECT MAX(run_utc) FROM {SCHEMA}.completed_runs)
                ) review
        LEFT JOIN {SCHEMA}.eic_project_snapshots eic
          ON eic.run_utc = review.run_utc AND eic.project_id = review.project_id
        LEFT JOIN {SCHEMA}.salesforce_opportunity_snapshots sf
          ON sf.run_utc = review.run_utc AND sf.opportunity_id = candidate_id
    """)
    spark.sql(f"""
        CREATE OR REPLACE VIEW {SCHEMA}.project_overview_current AS
        SELECT project.*, review.opportunity_id, review.opportunity_name,
            review.opportunity_subtype, review.candidate_ids, review.candidate_names,
            review.candidate_countries, review.candidate_subtypes, review.candidate_scores,
            review.best_candidate_score, review.match_status, review.review_required,
            review.decision_source, review.reason, review.llm_evidence
        FROM {SCHEMA}.eic_projects_current project
        JOIN {SCHEMA}.match_review_current review
          ON project.run_utc = review.run_utc AND project.project_id = review.project_id
    """)
    if screen_frame is not None:
        spark.sql(f"""
            CREATE OR REPLACE VIEW {SCHEMA}.pair_label_queue_current AS
            SELECT screen.eic_project_id, eic.project_name AS eic_project_name, eic.country AS eic_country,
                eic.locality AS eic_locality, eic.operator_name AS eic_operator_name,
                eic.startup_year AS eic_startup_year, eic.status AS eic_status,
                eic.stage AS eic_stage,
                screen.salesforce_opportunity_id, sf.opportunity_name AS salesforce_opportunity_name,
                sf.country AS salesforce_country, sf.account_name AS salesforce_account_name,
                sf.region AS salesforce_region, sf.stage AS salesforce_stage,
                sf.estimated_first_delivery_year AS salesforce_estimated_first_delivery_year,
                sf.phase_year AS salesforce_phase_year,
                sf.source_last_modified_at AS salesforce_last_modified_at,
                screen.screen_reason, screen.candidate_score, screen.last_screened_run_utc
            FROM {SCHEMA}.pair_screen_current screen
            JOIN {SCHEMA}.eic_projects_current eic ON eic.project_id = screen.eic_project_id
            JOIN {SCHEMA}.salesforce_opportunities_current sf
              ON sf.opportunity_id = screen.salesforce_opportunity_id
            LEFT ANTI JOIN {SCHEMA}.pair_labels labelled
              ON labelled.eic_project_id = screen.eic_project_id
             AND labelled.salesforce_opportunity_id = screen.salesforce_opportunity_id
             AND labelled.reviewer IS NOT NULL AND labelled.is_match IS NOT NULL
            WHERE screen.screen_reason = 'candidate'
               OR (screen.screen_reason = 'low_name_score'
                   AND pmod(xxhash64(screen.eic_project_id, screen.salesforce_opportunity_id), 100) = 0)
               OR (screen.screen_reason = 'weak_name_overlap'
                   AND pmod(xxhash64(screen.eic_project_id, screen.salesforce_opportunity_id), 1000) = 0)
               OR (screen.screen_reason = 'country_conflict'
                   AND pmod(xxhash64(screen.eic_project_id, screen.salesforce_opportunity_id), 5000) = 0)
               OR (screen.screen_reason = 'no_name_overlap'
                   AND pmod(xxhash64(screen.eic_project_id, screen.salesforce_opportunity_id), 10000) = 0)
        """)

    completed = spark.createDataFrame([(
        run_id, match_summary["total_projects"],
        subtype_counts["Oil&Gas"] + subtype_counts["Gas"],
        subtype_counts["Oil&Gas"], subtype_counts["Gas"],
        match_summary["llm_calls"], match_summary["matched"], match_summary["partial"],
        match_summary["uncertain"], match_summary["new_candidates"],
        screen_plan["screened_pairs"] if screen_plan is not None else None,
        screen_plan["possible_pairs"] if screen_plan is not None else None,
        SCREENING_VERSION if screen_plan is not None else None,
        screen_plan.get("new_eic_projects") if screen_plan is not None else None,
        screen_plan.get("modified_eic_projects") if screen_plan is not None else None,
        screen_plan.get("new_salesforce_opportunities") if screen_plan is not None else None,
        screen_plan.get("modified_salesforce_opportunities") if screen_plan is not None else None,
        match_summary.get("candidate_pairs"), match_summary.get("completed_pairs"),
        match_summary.get("pending_pairs"), match_summary.get("llm_errors"),
    )], schema=(
        "run_utc STRING, eic_projects BIGINT, salesforce_opportunities BIGINT, "
        "oil_gas_opportunities BIGINT, gas_opportunities BIGINT, llm_calls BIGINT, "
        "matched BIGINT, partial BIGINT, uncertain BIGINT, new_candidates BIGINT, "
        "screened_pairs BIGINT, possible_pairs BIGINT, screening_version STRING, "
        "new_eic_projects BIGINT, modified_eic_projects BIGINT, "
        "new_salesforce_opportunities BIGINT, modified_salesforce_opportunities BIGINT, "
        "candidate_pairs BIGINT, completed_pairs BIGINT, pending_pairs BIGINT, llm_errors BIGINT"
    )).withColumn("completed_at_utc", F.current_timestamp())
    (completed.write.format("delta").mode("append").option("mergeSchema", "true")
     .saveAsTable(f"{SCHEMA}.completed_runs"))