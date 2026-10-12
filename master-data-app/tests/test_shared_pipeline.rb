require 'psych'

project_root = File.expand_path('..', __dir__)
shared_template = 'pipelines/templates/deploy_databricks.yml@da-mdp-foundations-deployments'
expected_parameters = {
  'env' => '${{ variables.PIPELINE_ENV }}',
  'envLong' => '${{ variables.ENV_LONG }}',
  'subscriptionName' => '${{ variables.SUBSCRIPTION_NAME }}',
  'keyVaultName' => '${{ variables.KEYVAULT_NAME }}',
  'spnIdSecretName' => '${{ variables.SPN_ID_SECRET_NAME }}',
  'spnSecretSecretName' => '${{ variables.SPN_SECRET_SECRET_NAME }}',
  'tenantIdSecretName' => '${{ variables.TENANT_SECRET_NAME }}',
  'adbHostnameSecretName' => '${{ variables.ADB_HOST_SECRET_NAME }}',
  'dbxProfile' => '${{ variables.DBX_PROFILE }}',
  'enablePostDeploy' => true,
  'enableRollbackOnFailure' => true
}

%w[ACC PRD].each do |environment|
  path = File.join(project_root, "pipelines/Automation_Deploy_Databricks_#{environment}.yml")
  pipeline = Psych.load_file(path)
  stages = pipeline.fetch('stages')
  raise 'Unexpected project-specific deployment stage' unless stages.length == 1
  raise 'Shared deployment template changed' unless stages.first.fetch('template') == shared_template
  raise 'Shared deployment parameters changed' unless stages.first.fetch('parameters') == expected_parameters
  variable_template = "variables/databricks_variables_#{environment.downcase}.yml"
  raise 'Environment variables changed' unless pipeline.fetch('variables') == [{'template' => variable_template}]
  raise 'Unexpected custom app template reference' if File.read(path).include?('deploy_master_data_app')
  expected_trigger = environment == 'ACC' ? 'none' : {
    'branches' => {'include' => ['main']},
    'paths' => {'exclude' => ['*.md', 'pipelines/**']}
  }
  raise 'Pipeline trigger changed' unless pipeline.fetch('trigger') == expected_trigger
  puts "Passed: #{environment} uses only the existing shared deployment template, original parameters and original trigger"
end

custom_template = File.join(project_root, 'pipelines/templates/deploy_master_data_app.yml')
raise 'Custom app template still exists' if File.exist?(custom_template)
puts 'Shared pipeline source checks passed. Azure DevOps template compilation is not exercised by this test.'