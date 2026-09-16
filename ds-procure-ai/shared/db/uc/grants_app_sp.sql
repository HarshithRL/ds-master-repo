-- Run as catalog MANAGE admin for Mate ds-procure-ai cutover
-- App SP: a65ce6d4-0267-43b3-a6c4-b24c39a35d05

GRANT USE CATALOG ON CATALOG automation_d TO `a65ce6d4-0267-43b3-a6c4-b24c39a35d05`;
GRANT USE SCHEMA ON SCHEMA automation_d.bronze TO `a65ce6d4-0267-43b3-a6c4-b24c39a35d05`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME automation_d.bronze.bronze_volume TO `a65ce6d4-0267-43b3-a6c4-b24c39a35d05`;

-- ACC: intentionally NOT granted. Policy: the app SP must not hold direct
-- catalog/schema/volume access — UC/Volume/SQL-warehouse access goes through
-- visitor OBO (MATE_UC_AUTH=obo) only. Real users get access via their
-- AUTOMATION.DSPROCUREAI.CONSUMER.READ/WRITE group grants instead (already
-- applied in ACC). If OBO isn't bound for some call, it is expected to fail
-- closed (PERMISSION_DENIED) rather than silently succeed as the app SP.
-- ACC app SP for reference only: 8e7535ad-24ff-4f68-b6ee-eac9ee389dd4

-- Warehouse (CAN_USE) — requires SQL warehouse MANAGE (not UC SQL):
--   App SP: a65ce6d4-0267-43b3-a6c4-b24c39a35d05
--   Warehouse: 69ada62b2fb9b9e2 (dau-automation-sqlwh-d-01)
-- Via UI: SQL warehouses → Permissions → add app SP CAN_USE
-- Or CLI (warehouse owner/admin):
--   databricks warehouses update-permissions 69ada62b2fb9b9e2 -p <profile> --json @wh_sp_can_use.json
-- where wh_sp_can_use.json merges existing ACL + service_principal_name with CAN_USE.
