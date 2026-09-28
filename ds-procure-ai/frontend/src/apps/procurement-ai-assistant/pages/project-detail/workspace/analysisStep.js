/**
 * Which rail step is current.
 *
 * Pure so the gate logic can be tested without rendering: the bug it exists to
 * prevent only shows up after a remount, which a render test would hide.
 */
export function analysisStep({
  fileCount = 0,
  kbBuilding = false,
  kbFailed = false,
  blockingCount = 0,
  skippedGaps = false,
  xlsxBusy = false,
  xlsxWritten = false,
  xlsxReady = false,
  pptReady = false,
} = {}) {
  let step = "upload";
  if (fileCount > 0) step = "kb";
  if (kbFailed) return "kb";
  if (kbBuilding || fileCount === 0) return step;

  step = "gaps";
  // Only blocking gaps gate. skippedGaps is per-mount state, so an optional
  // gap used to pin the rail on step 3 again after every reload.
  if (skippedGaps || blockingCount === 0) step = "xlsx";
  // A started run is server-side proof the gate was answered, and unlike
  // skippedGaps it survives navigating away and back.
  if (xlsxBusy || xlsxWritten) step = "xlsx";
  if (xlsxReady) step = "ppt";
  if (pptReady) step = "done";
  return step;
}
