import assert from "node:assert/strict";
import test from "node:test";

import { xlsxIsFilled, xlsxIsWritten } from "./packStatus.js";

test("template is written but not filled — UI can offer download without unlocking PPT", () => {
  assert.equal(xlsxIsWritten("template"), true);
  assert.equal(xlsxIsFilled("template"), false);
});

test("ready is written and filled", () => {
  assert.equal(xlsxIsWritten("ready"), true);
  assert.equal(xlsxIsFilled("ready"), true);
});

test("idle is neither written nor filled", () => {
  assert.equal(xlsxIsWritten("idle"), false);
  assert.equal(xlsxIsFilled("idle"), false);
});
