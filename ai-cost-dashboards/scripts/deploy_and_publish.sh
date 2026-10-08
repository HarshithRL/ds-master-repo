#!/usr/bin/env bash
set -euo pipefail

target="${1:-}"
profile="${2:-${DATABRICKS_CONFIG_PROFILE:-}}"

if [[ -z "$target" ]]; then
  echo "Usage: bash scripts/deploy_and_publish.sh <D|T|A|P> [profile]" >&2
  exit 2
fi

bundle_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$bundle_root"

profile_args=()
if [[ -n "$profile" ]]; then
  profile_args=(--profile "$profile")
fi

databricks bundle deploy --target "$target" --auto-approve "${profile_args[@]}"

state_file=".databricks/bundle/${target}/resources.json"
if [[ ! -f "$state_file" ]]; then
  echo "Bundle state was not created: $state_file" >&2
  exit 1
fi

for resource_key in azure_cost_detail etex_ai_cost_executive_overview; do
  dashboard_id="$(jq -er ".state[\"resources.dashboards.${resource_key}\"].__id__" "$state_file")"
  databricks lakeview publish "$dashboard_id" "${profile_args[@]}"
done