require 'minitest/autorun'
require 'yaml'

class DeploymentConfigTest < Minitest::Test
  ROOT = File.expand_path('..', __dir__)
  GROUPS = %w[AUTOMATION.DSPMO.CONSUMER.READ AUTOMATION.DSPMO.CONSUMER.WRITE].freeze
  WAREHOUSES = {
    'D' => ['automation_d', '69ada62b2fb9b9e2'],
    'T' => ['automation_d', '69ada62b2fb9b9e2'],
    'A' => ['automation_a', 'ab42869e34018a6e'],
    'P' => ['automation_p', '4d5f9389063a8264']
  }.freeze

  def setup
    @bundle = YAML.load_file(File.join(ROOT, 'databricks.yml'))
    @consumer = YAML.load_file(File.join(ROOT, 'resources/apps/consumer.permissions.yml'))
    @app = YAML.load_file(File.join(ROOT, 'resources/apps/pmo.app.yml')).fetch('resources').fetch('apps').fetch('pmo')
  end

  def test_target_warehouses_match_owner_supplied_connections
    assert_equal WAREHOUSES.keys.sort, @bundle.fetch('targets').keys.sort
    WAREHOUSES.each do |target, expected|
      variables = @bundle.fetch('targets').fetch(target).fetch('variables')
      assert_equal expected, [variables.fetch('catalog'), variables.fetch('warehouse_id')], target
    end
  end

  def test_consumer_permissions_are_explicitly_included_without_a_broad_glob
    assert_equal [
      'resources/apps/pmo.app.yml',
      'resources/apps/consumer.permissions.yml',
      'resources/jobs/pmo_setup.job.yml',
      'resources/jobs/pmo_migration.job.yml'
    ], @bundle.fetch('include')
    assert_equal %w[A P], @consumer.fetch('targets').keys.sort
    @consumer.fetch('targets').each do |target, config|
      app = config.fetch('resources').fetch('apps').fetch('pmo')
      assert_equal '${var.app_name}', app.fetch('name'), target
      permissions = app.fetch('permissions')
      assert_equal GROUPS.map { |group| { 'group_name' => group, 'level' => 'CAN_USE' } }, permissions, target
    end
  end

  def test_named_app_permissions_and_managers_are_retained
    permissions = @app.fetch('permissions')
    assert_equal %w[mustafaarda.bicakci@etexgroup.com pierre.delaguiche@etexgroup.com],
                 permissions.select { |permission| permission['level'] == 'CAN_MANAGE' }.map { |permission| permission['user_name'] }
    visitors = %w[arne.rotty@etexgroup.com luc.vautmans@etexgroup.com hugo.reis@etexgroup.com
                  alberto.olmos@etexgroup.com patricio.vega@etexgroup.com kerem.yenideniz@etexgroup.com
                  yusakayra.saltan@etexgroup.com]
    assert_equal visitors, permissions.select { |permission| permission['level'] == 'CAN_USE' }.map { |permission| permission['user_name'] }
    assert_equal permissions.length, permissions.map { |permission| permission['user_name'] }.uniq.length
    assert permissions.none? { |permission| permission.key?('group_name') }
  end

  def test_app_and_setup_job_follow_the_target_warehouse_and_delegated_sql_scope
    environment = @app.fetch('config').fetch('env').to_h { |entry| [entry.fetch('name'), entry.fetch('value')] }
    assert_equal '/sql/1.0/warehouses/${var.warehouse_id}', environment.fetch('DATABRICKS_WAREHOUSE_HTTP_PATH')
    assert_equal '${var.catalog}', environment.fetch('DATABRICKS_CATALOG')
    assert_equal ['sql'], @app.fetch('user_api_scopes')
    setup_job = YAML.load_file(File.join(ROOT, 'resources/jobs/pmo_setup.job.yml'))
    task = setup_job.fetch('resources').fetch('jobs').fetch('pmo_setup').fetch('tasks').first
    assert_equal '${var.warehouse_id}', task.fetch('sql_task').fetch('warehouse_id')
  end
end