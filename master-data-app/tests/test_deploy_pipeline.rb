require 'psych'
require 'open3'
require 'tmpdir'

project_root = File.expand_path('..', __dir__)
template_path = File.join(project_root, 'pipelines/templates/deploy_master_data_app.yml')
template = Psych.load_file(template_path)
stage = template.fetch('stages').first
job = stage.fetch('jobs').first
steps = job.fetch('strategy').fetch('runOnce').fetch('deploy').fetch('steps')

raise 'Failure/cancellation gate changed' unless stage.fetch('condition') == 'and(not(failed()), not(canceled()))'
raise 'Environment approval gate missing' unless job.fetch('environment') == '${{ variables.PIPELINE_ENV }}'
raise 'Checkout path mismatch' unless steps.first.fetch('path') == 's/DS-Master-Repo'
raise 'Working directory mismatch' unless steps.last.fetch('workingDirectory') == '$(Pipeline.Workspace)/s/DS-Master-Repo/master-data-app'

{'ACC' => 'A', 'PRD' => 'P'}.each do |environment, target|
  pipeline = Psych.load_file(File.join(project_root, "pipelines/Automation_Deploy_Databricks_#{environment}.yml"))
  integration = pipeline.fetch('stages').last
  raise 'Wrong app stage integration' unless integration.fetch('template') == 'templates/deploy_master_data_app.yml'
  raise 'Wrong deployment target' unless integration.fetch('parameters').fetch('target') == target
end

steps.select { |step| step.key?('bash') }.each do |step|
  IO.popen(['/bin/bash', '-n'], 'w') { |shell| shell.write(step.fetch('bash')) }
  raise "Invalid shell: #{step.fetch('displayName')}" unless $?.success?
end

mock = <<~'BASH'
  databricks() {
    printf 'MOCK:%s\n' "$1 $2" >&2
    case "$1 $2" in
      "bundle deploy")
        [[ "$*" == "bundle deploy --target $BUNDLE_TARGET --auto-approve" ]] || return 91
        return "$MOCK_BUNDLE_EXIT"
        ;;
      "apps deploy")
        [[ "$*" == "apps deploy ds-master-data-app --source-code-path /Workspace/automation/ds-master-data-app/$BUNDLE_TARGET/files/src" ]] || return 92
        return "$MOCK_DEPLOY_EXIT"
        ;;
      "apps get")
        [[ "$*" == "apps get ds-master-data-app --output json" ]] || return 93
        printf '{"app_status":{"state":"%s"}}\n' "$MOCK_RUNTIME_STATE"
        ;;
      *) return 94 ;;
    esac
  }
BASH

hosts = {
  'T' => 'https://adb-7181820732839861.1.azuredatabricks.net',
  'A' => 'https://adb-4796304964978539.19.azuredatabricks.net',
  'P' => 'https://adb-4844910598668398.18.azuredatabricks.net'
}
scenarios = hosts.map { |target, host| [target, host, '0', '0', 'RUNNING', true] }
scenarios.concat([
  ['A', hosts.fetch('A'), '1', '0', 'RUNNING', false],
  ['A', hosts.fetch('A'), '0', '1', 'RUNNING', false],
  ['A', hosts.fetch('A'), '0', '0', 'UNAVAILABLE', false],
  ['A', hosts.fetch('P'), '0', '0', 'RUNNING', false]
])

Dir.mktmpdir('master-data-pipeline-test-') do |directory|
  script = steps.last.fetch('bash').gsub('$(Agent.TempDirectory)', directory)
  scenarios.each do |target, host, bundle_exit, deploy_exit, runtime, expected_success|
    environment = {
      'PATH' => ENV.fetch('PATH'),
      'BUNDLE_TARGET' => target,
      'DATABRICKS_HOST' => host,
      'MOCK_BUNDLE_EXIT' => bundle_exit,
      'MOCK_DEPLOY_EXIT' => deploy_exit,
      'MOCK_RUNTIME_STATE' => runtime
    }
    output, error, result = Open3.capture3(environment, '/bin/bash', stdin_data: mock + script)
    raise "Unexpected result: #{output} #{error}" unless result.success? == expected_success
    calls = error.lines.grep(/^MOCK:/).map(&:strip)
    expected_calls = if host != hosts.fetch(target)
                       []
                     elsif bundle_exit != '0'
                       ['MOCK:bundle deploy']
                     elsif deploy_exit != '0'
                       ['MOCK:bundle deploy', 'MOCK:apps deploy']
                     else
                       ['MOCK:bundle deploy', 'MOCK:apps deploy', 'MOCK:apps get']
                     end
    raise "Wrong command ordering: #{calls}" unless calls == expected_calls
    puts "Passed: target=#{target}, bundle_exit=#{bundle_exit}, deploy_exit=#{deploy_exit}, app=#{runtime}, matching_host=#{host == hosts.fetch(target)}"
  end
end

puts 'Pipeline integration, YAML, shell and seven mocked deployment scenarios passed.'