import { expect, it } from "vitest";
import ExcelJS from "exceljs";

it("roundtrips a real workbook with the patched UUID dependency", async () => {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("PMO validation");
  sheet.addRow(["Project", "Budget"]);
  sheet.addRow(["Validation", 123.45]);
  sheet.addConditionalFormatting({
    ref: "B2:B2",
    rules: [{ type: "dataBar", priority: 1, cfvo: [{ type: "min" }, { type: "max" }] }],
  });
  const bytes = await workbook.xlsx.writeBuffer();
  expect(bytes.byteLength).toBeGreaterThan(1000);
  const loaded = new ExcelJS.Workbook();
  await loaded.xlsx.load(bytes);
  expect(loaded.getWorksheet("PMO validation")?.getCell("A2").value).toBe("Validation");
  expect(loaded.getWorksheet("PMO validation")?.getCell("B2").value).toBe(123.45);
});