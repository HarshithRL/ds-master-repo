# Etex PMO

Project portfolio management for Etex, hosted in Databricks Apps and delivered as the `ds-pmo` bundle in DS-Master-Repo. See [PRODUCTION.md](PRODUCTION.md) for the environment matrix, rollout order and security acceptance boundaries.

## Stack

- **Next.js 16** (App Router) + **React 19** + **TypeScript 5**
- **Tailwind CSS 4** + Radix UI primitives
- **Databricks SQL** with 18 Delta tables in the existing `automation_d/a/p.silver` schema, all prefixed `PMO_`
- **Entra / Databricks Apps** authentication with delegated SQL user authorization and pre-provisioned active PMO users
- **Databricks Jobs** for additive table setup and initial admin bootstrap
- Transactional email disabled pending approved service configuration
- **Vitest** for tests
- **Node 22** standalone server, built and started by the included app resource

## Develop

```bash
npm ci
npm test
npm run schema:check
node --experimental-strip-types --test tests/table-names.test.mjs
npm run build
databricks bundle validate -t D --profile DEFAULT
```

DEV: https://ds-pmo-dev-7181820732839861.1.azure.databricksapps.com

The D target explicitly includes both the app and setup job. ACC/PRD promotion uses the existing shared repository pipeline. Run the setup job after deployment and before central consumer grants. No catalog/schema is created and no original sandbox data is automatically copied.

## Initial Data Migration

The bundle also explicitly includes a DEV-only export job and a D/T/A/P volume import job. The export captures all 18 original tables as checksummed, lossless CSV files and a single portable ZIP in `/Volumes/automation_d/bronze/bronze_volume/pmo_app/`. Copy that ZIP to the corresponding existing volume folder in ACC/PRD, promote the code through the existing pipeline, then run import validation before an explicitly approved apply. Nothing runs automatically on deployment. See [migration/README.md](migration/README.md) for the exact paths, job parameters, source authorization approval and rerun rules.

Migration tests: `python -m unittest discover -s tests -p test_migration.py -v`. The standard-library tests cover file integrity, NULL/date/JSON roundtrips, relationship checks, bootstrap safety, read-only validation and insert-only import orchestration.

Do not treat a local Node server as a secure substitute for the Databricks Apps identity proxy. Browser acceptance requires Entra login and SQL consent. The production guide documents the distinction between application-level project permissions and direct SQL privileges, and why consumer group ACL activation is deferred until groups exist.

For the opt-in DEV-only native SQL checks, run `PMO_NATIVE_DEV_TEST=true npm test -- src/lib/__tests__/native-dev.test.ts`. It uses the local DEFAULT CLI credential without printing it, verifies the DEV identity, and cleans up its uniquely identified probe row. It never runs against ACC/PRD.

## Author

Original application credited to Facundo Cosimo, <facundocosimo@gmail.com>.
