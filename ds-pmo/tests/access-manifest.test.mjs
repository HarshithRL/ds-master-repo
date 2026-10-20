import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import test from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../../permissions/access.json", import.meta.url), "utf8"));
const expectedMembers = [
  "mustafaarda.bicakci@etexgroup.com",
  "arne.rotty@etexgroup.com",
  "luc.vautmans@etexgroup.com",
  "hugo.reis@etexgroup.com",
  "alberto.olmos@etexgroup.com",
  "patricio.vega@etexgroup.com",
  "kerem.yenideniz@etexgroup.com",
  "yusakayra.saltan@etexgroup.com",
];
const matches = manifest.data_products.filter((product) => product.data_product === "ds-pmo");

test("PMO access product matches the actual bundle folder", () => {
  assert.equal(matches.length, 1);
  assert(!manifest.data_products.some((product) => product.data_product === "pmo"));
  assert(existsSync(new URL(`../../${matches[0].data_product}/databricks.yml`, import.meta.url)));
  assert.equal(matches[0].warehouse, true);
});

for (const tier of ["READ", "WRITE"]) {
  test(`${tier} includes all requested PMO users without duplicate membership`, () => {
    const groups = matches[0].consumer_groups.filter((group) => group.tier === tier);
    assert.equal(groups.length, 1);
    const group = groups[0];
    assert.equal(new Set(group.members).size, group.members.length);
    for (const email of expectedMembers) assert(group.members.includes(email), `${tier} missing ${email}`);
  });

  test(`${tier} retains the PMO table scope and required volume permissions`, () => {
    const group = matches[0].consumer_groups.find((entry) => entry.tier === tier);
    const tables = group.grants.filter((grant) => grant.table);
    assert.equal(tables.length, 18);
    assert.equal(new Set(tables.map((grant) => grant.table)).size, 18);
    for (const grant of tables) {
      assert.equal(grant.catalog, "automation");
      assert.equal(grant.schema, "silver");
      assert(grant.table.startsWith("PMO_"));
      assert.deepEqual(grant.privileges, tier === "READ" ? ["SELECT"] : ["SELECT", "MODIFY"]);
    }
    const volumes = group.grants.filter((grant) => grant.volume);
    assert.deepEqual(volumes, [{
      catalog: "automation", schema: "bronze", volume: "bronze_volume",
      privileges: tier === "READ" ? ["READ_VOLUME"] : ["READ_VOLUME", "WRITE_VOLUME"],
    }]);
    assert(group.grants.some((grant) => grant.catalog === "automation" && grant.schema === "bronze" && !grant.table && !grant.volume && grant.privileges.includes("USE_SCHEMA")));
    assert(!group.grants.some((grant) => grant.privileges.some((privilege) => /^(ALL_PRIVILEGES|MANAGE|CREATE_)/.test(privilege))));
  });
}