-- Run as catalog MANAGE admin for Mate ds-procure-ai cutover
-- App SP: a65ce6d4-0267-43b3-a6c4-b24c39a35d05

GRANT USE CATALOG ON CATALOG automation_d TO `a65ce6d4-0267-43b3-a6c4-b24c39a35d05`;
GRANT USE SCHEMA ON SCHEMA automation_d.bronze TO `a65ce6d4-0267-43b3-a6c4-b24c39a35d05`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME automation_d.bronze.bronze_volume TO `a65ce6d4-0267-43b3-a6c4-b24c39a35d05`;

-- ACC (when ready):
-- GRANT USE CATALOG ON CATALOG automation_a TO `<acc-app-sp>`;
-- GRANT USE SCHEMA ON SCHEMA automation_a.bronze TO `<acc-app-sp>`;
-- GRANT READ VOLUME, WRITE VOLUME ON VOLUME automation_a.bronze.bronze_volume TO `<acc-app-sp>`;

-- Warehouse (CAN_USE) — requires SQL warehouse MANAGE (not UC SQL):
--   App SP: a65ce6d4-0267-43b3-a6c4-b24c39a35d05
--   Warehouse: 69ada62b2fb9b9e2 (dau-automation-sqlwh-d-01)
-- Via UI: SQL warehouses → Permissions → add app SP CAN_USE
-- Or CLI (warehouse owner/admin):
--   databricks warehouses update-permissions 69ada62b2fb9b9e2 -p <profile> --json @wh_sp_can_use.json
-- where wh_sp_can_use.json merges existing ACL + service_principal_name with CAN_USE.
