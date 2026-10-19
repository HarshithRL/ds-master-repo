SELECT assert_true(:catalog IN ('automation_d', 'automation_a', 'automation_p'), 'Unsupported PMO catalog');

SELECT assert_true(lower(:initial_admin_email) RLIKE '^[^@\\s]+@etexgroup[.]com$', 'Initial admin must be an Etex identity');

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_users') (
  id STRING NOT NULL,
  email STRING,
  name STRING NOT NULL,
  image STRING,
  global_role STRING NOT NULL,
  permissions STRING,
  is_active BOOLEAN NOT NULL,
  email_verified TIMESTAMP,
  last_login_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_divisions') (
  id STRING NOT NULL,
  name STRING NOT NULL,
  is_active BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_factories') (
  id STRING NOT NULL,
  code STRING,
  name STRING NOT NULL,
  short_name STRING,
  country STRING,
  currency STRING,
  division_id STRING,
  is_active BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_categories') (
  id STRING NOT NULL,
  code STRING NOT NULL,
  name STRING NOT NULL,
  is_active BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_resources') (
  id STRING NOT NULL,
  category STRING NOT NULL,
  title STRING NOT NULL,
  description STRING,
  href STRING NOT NULL,
  format STRING,
  sort_order INT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_projects') (
  id STRING NOT NULL,
  reference STRING,
  name STRING NOT NULL,
  description STRING,
  objective STRING,
  scope STRING,
  scope_exclusions STRING,
  status STRING NOT NULL,
  tier STRING NOT NULL,
  lifecycle_type STRING NOT NULL,
  category_id STRING,
  factory_id STRING,
  wbs_codes STRING,
  current_phase STRING NOT NULL,
  current_gate STRING,
  key_achievements STRING,
  actual_start_date TIMESTAMP,
  planned_completion_date TIMESTAMP,
  expected_completion_date TIMESTAMP,
  rids_open INT,
  red_flags_open INT,
  rag_progress STRING,
  rag_schedule STRING,
  rag_cost STRING,
  rag_risk STRING,
  rag_scope STRING,
  rag_resources STRING,
  rag_progress_label STRING,
  rag_schedule_label STRING,
  rag_cost_label STRING,
  rag_risk_label STRING,
  rag_scope_label STRING,
  rag_resources_label STRING,
  total_float_excl_buffer DOUBLE,
  total_float_incl_buffer DOUBLE,
  resource_consumption_pct DOUBLE,
  total_cost DOUBLE,
  expected_value DOUBLE,
  roi DOUBLE,
  payback_years DOUBLE,
  risks_issues_count INT,
  risks_high_count INT,
  risks_moderate_count INT,
  risks_low_count INT,
  risks_identified_count INT,
  risks_quantified_count INT,
  total_cost_at_risk DOUBLE,
  total_time_impact DOUBLE,
  schedule_doc_url STRING,
  cost_doc_url STRING,
  riac_doc_url STRING,
  is_active BOOLEAN NOT NULL,
  flags STRING,
  is_confidential BOOLEAN,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  last_updated_by_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_project_assignments') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  user_id STRING NOT NULL,
  role STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_scope_grants') (
  id STRING NOT NULL,
  user_id STRING NOT NULL,
  division_id STRING,
  factory_id STRING,
  created_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_budgets') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  bac DOUBLE NOT NULL,
  actuals DOUBLE NOT NULL,
  committed DOUBLE NOT NULL,
  expected DOUBLE NOT NULL,
  risk_contingency_budgeted DOUBLE NOT NULL,
  risk_contingency_consumed DOUBLE NOT NULL,
  mgmt_contingency_budgeted DOUBLE NOT NULL,
  mgmt_contingency_consumed DOUBLE NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_budget_lines') (
  id STRING NOT NULL,
  budget_id STRING NOT NULL,
  type STRING NOT NULL,
  year INT NOT NULL,
  amount DOUBLE NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_gate_records') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  gate STRING NOT NULL,
  status STRING NOT NULL,
  planned_date TIMESTAMP,
  completed_date TIMESTAMP,
  notes STRING,
  updated_by_id STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_risks') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  risk_number INT,
  type STRING NOT NULL,
  risk_statement STRING NOT NULL,
  if_clause STRING,
  due_to_clause STRING,
  then_clause STRING,
  impact STRING NOT NULL,
  category STRING,
  probability DOUBLE,
  cost_impact DOUBLE,
  time_impact DOUBLE,
  weight DOUBLE,
  counter_measures STRING,
  response_strategy STRING,
  completion_date TIMESTAMP,
  owner_name STRING,
  status STRING NOT NULL,
  comments STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_milestones') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  name STRING NOT NULL,
  target_date TIMESTAMP,
  expected_date TIMESTAMP,
  remarks STRING,
  sort_order INT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_planned_actions') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  action STRING NOT NULL,
  owner_label STRING,
  by_date TIMESTAMP,
  status STRING NOT NULL,
  notes STRING,
  sort_order INT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_scope_changes') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  submitted_date TIMESTAMP,
  description STRING NOT NULL,
  impact_cost STRING,
  impact_schedule STRING,
  impact_cost_value DOUBLE,
  impact_schedule_value DOUBLE,
  status STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_project_documents') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  name STRING NOT NULL,
  url STRING NOT NULL,
  sort_order INT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_project_snapshots') (
  id STRING NOT NULL,
  project_id STRING NOT NULL,
  project_reference STRING NOT NULL,
  project_name STRING NOT NULL,
  period_label STRING NOT NULL,
  notes STRING,
  created_by_id STRING,
  created_at TIMESTAMP NOT NULL,
  current_phase STRING,
  progress DOUBLE,
  current_b_a_c DOUBLE,
  eac DOUBLE,
  actual_cost DOUBLE,
  committed DOUBLE,
  risk_contingency_budgeted DOUBLE,
  risk_contingency_consumed DOUBLE,
  mgmt_contingency_budgeted DOUBLE,
  mgmt_contingency_consumed DOUBLE,
  variance_at_completion DOUBLE,
  schedule_buffer DOUBLE,
  rag_progress STRING,
  rag_schedule STRING,
  rag_cost STRING,
  rag_risk STRING,
  rag_scope STRING,
  rag_resources STRING,
  rag_progress_label STRING,
  rag_schedule_label STRING,
  rag_cost_label STRING,
  rag_risk_label STRING,
  rag_scope_label STRING,
  rag_resources_label STRING,
  rids_open INT,
  red_flags_open INT,
  total_float_excl_buffer DOUBLE,
  total_float_incl_buffer DOUBLE,
  resource_consumption_pct DOUBLE,
  open_risk_count INT,
  open_issue_count INT,
  total_cost_at_risk DOUBLE,
  total_time_impact DOUBLE,
  planned_completion_date TIMESTAMP,
  expected_completion_date TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_audit_logs') (
  id STRING NOT NULL,
  user_id STRING,
  project_id STRING,
  action STRING NOT NULL,
  entity STRING NOT NULL,
  entity_id STRING,
  changes STRING,
  created_at TIMESTAMP NOT NULL
) USING DELTA;

MERGE INTO IDENTIFIER(:catalog || '.silver.PMO_users') AS target
USING (SELECT lower(:initial_admin_email) AS email) AS source
ON lower(target.email) = source.email
WHEN NOT MATCHED THEN INSERT (id, email, name, image, global_role, permissions, is_active, last_login_at, created_at, updated_at)
VALUES (uuid(), source.email, source.email, NULL, 'ADMIN', '[]', true, NULL, current_timestamp(), current_timestamp());
