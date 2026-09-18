import assert from "node:assert/strict";
import test from "node:test";

import { shouldContinueInsightsPoll } from "./kbStatus.js";

test("polls while knowledge base is building", () => {
  assert.equal(shouldContinueInsightsPoll("ingesting"), true);
  assert.equal(shouldContinueInsightsPoll("building"), true);
  assert.equal(shouldContinueInsightsPoll("staged"), true);
  assert.equal(shouldContinueInsightsPoll("extracting"), true);
});

test("stops polling when knowledge base is idle", () => {
  assert.equal(shouldContinueInsightsPoll("ready"), false);
  assert.equal(shouldContinueInsightsPoll("empty"), false);
  assert.equal(shouldContinueInsightsPoll("failed"), false);
  assert.equal(shouldContinueInsightsPoll(null), false);
});

test("keeps polling while a file upload is in progress", () => {
  assert.equal(shouldContinueInsightsPoll("ready", true), true);
  assert.equal(shouldContinueInsightsPoll("empty", true), true);
});
