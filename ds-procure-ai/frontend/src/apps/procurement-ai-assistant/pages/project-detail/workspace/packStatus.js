export function xlsxIsFilled(status) {
  return status === "ready";
}

export function xlsxIsWritten(status) {
  return status === "ready" || status === "template";
}

export function xlsxIsBuilding(status) {
  return status === "running";
}
