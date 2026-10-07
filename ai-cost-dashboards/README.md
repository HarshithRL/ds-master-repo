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

This bundle does not own or create source tables. `ai_foundry_costs_enriched` is
an upstream Azure-cost data product, while the retained `copilot-dashboard`
bundle owns the Copilot credit metric view. Each target must have those source
objects and grant dashboard viewers the necessary Unity Catalog access.