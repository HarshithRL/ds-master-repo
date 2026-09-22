import assert from "node:assert/strict";
import test from "node:test";

import { analysisStep } from "./analysisStep.js";

// The reported bug: a comparison was running, the user visited another page and
// came back, and the rail dropped to step 3 asking for the NDA again.
test("a running build keeps the rail on Excel after a remount clears skippedGaps", () => {
  const afterRemount = {
    fileCount: 6,
    blockingCount: 1, // NDA still missing
    skippedGaps: false, // per-mount state, gone after navigating away
    xlsxBusy: true, // server still says running
  };
  assert.equal(analysisStep(afterRemount), "xlsx");
});

test("without a run in flight the blocking gate still holds", () => {
  assert.equal(
    analysisStep({ fileCount: 6, blockingCount: 1, skippedGaps: false }),
    "gaps",
  );
});

test("continuing with gaps moves past the gate in the same mount", () => {
  assert.equal(
    analysisStep({ fileCount: 6, blockingCount: 1, skippedGaps: true }),
    "xlsx",
  );
});

test("no blocking gap means no gate at all", () => {
  assert.equal(analysisStep({ fileCount: 6, blockingCount: 0 }), "xlsx");
});

test("a workbook already written survives a remount too", () => {
  assert.equal(
    analysisStep({ fileCount: 6, blockingCount: 1, xlsxWritten: true }),
    "xlsx",
  );
});

test("a finished workbook advances to the deck step", () => {
  assert.equal(
    analysisStep({ fileCount: 6, blockingCount: 1, xlsxBusy: true, xlsxReady: true }),
    "ppt",
  );
});

test("a finished deck is done", () => {
  assert.equal(
    analysisStep({ fileCount: 6, xlsxReady: true, pptReady: true }),
    "done",
  );
});

// Behaviour that existed before the fix and must not change.
test("no files means the first step", () => {
  assert.equal(analysisStep({ fileCount: 0 }), "upload");
  assert.equal(analysisStep({ fileCount: 0, kbBuilding: true }), "upload");
});

test("a knowledge base build pins the rail on step 2", () => {
  assert.equal(analysisStep({ fileCount: 6, kbBuilding: true }), "kb");
});

test("a failed knowledge base pins the rail on step 2 even with a workbook", () => {
  assert.equal(
    analysisStep({ fileCount: 6, kbFailed: true, xlsxReady: true, pptReady: true }),
    "kb",
  );
});
