#!/usr/bin/env bash
set -euo pipefail

target="${1:?Usage: deploy_and_publish.sh D|T|A|P [profile]}"
case "$target" in
  D|T) default_profile=DEFAULT ;;
  A) default_profile=ACC ;;
  P) default_profile=PRD ;;
  *) printf 'Invalid target: %s\n' "$target" >&2; exit 2 ;;
esac
profile="${2:-$default_profile}"
python_executable="${PYTHON_EXECUTABLE:-python3}"
cd "$(dirname "$0")/.."
"$python_executable" scripts/render_dashboard_resources.py --check
"$python_executable" -m unittest discover -s tests -v
databricks bundle validate --target "$target" --profile "$profile"
databricks bundle deploy --target "$target" --profile "$profile"
for key in industry_open_orders industry_quotations; do
  dashboard_id="$(databricks bundle summary --target "$target" --profile "$profile" --output json | jq -er --arg key "$key" '.resources.dashboards[$key].id')"
  databricks lakeview publish "$dashboard_id" --profile "$profile" --json '{"embed_credentials":false}'
done
databricks bundle run industry_sales_refresh --target "$target" --profile "$profile"