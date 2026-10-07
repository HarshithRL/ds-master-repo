#!/usr/bin/env bash
set -euo pipefail

bundle_root="$(cd "$(dirname "$0")/.." && pwd)"

render_dashboard() {
  local resource_key="$1"
  local display_name="$2"
  local source_file="$3"
  local output_file="$4"

  {
    printf 'resources:\n'
    printf '  dashboards:\n'
    printf '    %s:\n' "$resource_key"
    printf '      display_name: "%s"\n' "$display_name"
    printf '      serialized_dashboard: |-\n'
    sed 's/^/        /' "$source_file"
    printf '\n'
    printf '      warehouse_id: ${var.warehouse_id}\n'
  } > "$output_file"
}

render_dashboard \
  etex_ai_cost_executive_overview \
  'Etex AI Cost Executive Overview' \
  "$bundle_root/src/dashboards/etex_ai_cost_executive_overview.lvdash.template" \
  "$bundle_root/resources/dashboards/etex_ai_cost_executive_overview.dashboard.yml"

render_dashboard \
  azure_cost_detail \
  'AI Cost Dashboard' \
  "$bundle_root/src/dashboards/azure_cost_detail.lvdash.template" \
  "$bundle_root/resources/dashboards/azure_cost_detail.dashboard.yml"