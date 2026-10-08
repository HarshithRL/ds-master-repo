# AI Cost Dashboards

This bundle deploys the following AI/BI dashboards together:

- Etex AI Cost Executive Overview
- AI Cost Dashboard (Azure cost detail)

The dashboard JSON uses `${var.catalog}` for all environment-owned source data.
The Executive Overview Azure detail link uses the deployed `azure_cost_detail`
resource ID and the target workspace host, so it always points to the detail
dashboard in the same environment.

Dashboard JSON is stored in `src/dashboards` as `.lvdash.template` files. The
neutral extension keeps the Workspace importer from treating a source template
as a live dashboard. Regenerate the
checked-in dashboard resource files after changing either template:

```sh
bash scripts/render_dashboard_resources.sh
```

The renderer uses `serialized_dashboard` rather than `file_path`: bundle
substitutions are resolved in resource configuration, but not within a
`.lvdash.json` file referenced by `file_path`.

| Target | Catalog | Workspace |
| --- | --- | --- |
| `D` | `automation_d` | Development |
| `T` | `automation_d` | Test |
| `A` | `automation_a` | Acceptance |
| `P` | `automation_p` | Production |

Validate, deploy, and publish:

```sh
databricks bundle validate --target <D|T|A|P>
bash scripts/deploy_and_publish.sh <D|T|A|P> [profile]
```

`deploy_and_publish.sh` deploys the bundle, reads the deployed dashboard IDs
from its target state, and publishes both dashboards. The shared Azure DevOps
template must invoke this script instead of only `databricks bundle deploy`;
deploying a Lakeview draft alone does not refresh its published revision.

## Azure cost refresh

The bundle owns the `azure_cost_enrichment` job. It verifies the target's fixed
`bronze` and `gold` schemas, exposes the configured Azure actual-cost source as
`bronze.azure_actual_cost`, and creates or refreshes the following objects:

- `gold.rg_tag_mapping_v`
- `gold.ai_foundry_costs_enriched`

It does not create, alter, or drop schemas. The Azure source is supplied
explicitly per target: D/T use the verified
`ingestion_azure_p.costs.azure_actual_cost` binding; A/P use their respective
`ingestion_azure_a` and `ingestion_azure_p` source tables.

D/T deploy a paused, non-writing job to protect the existing
`automation_d.gold.ai_foundry_costs_enriched` producer. A/P jobs run daily at
06:00 Europe/Brussels. Run the A/P job manually after deployment and verify its
preflight checks before relying on the scheduled refresh.

The retained `copilot-dashboard` bundle remains the owner of
`silver.metric_credit_consumption_v2`. Each target still needs Unity Catalog
grants for the job identity and dashboard viewers.