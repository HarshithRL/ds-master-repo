import { kbIsBuilding, kbStatusCopy } from "./workspace/kbStatus";

function KbStatusBanner({ kbStatus, kbMessage, emptyHint }) {
  const building = kbIsBuilding(kbStatus);
  const copy = kbStatusCopy(kbStatus, kbMessage);
  if (building && copy) {
    return <p className="kb-status-banner">{copy}</p>;
  }
  if (kbStatus === "failed") {
    return <p className="kb-status-banner is-error">{copy || "Knowledge base build failed."}</p>;
  }
  if (emptyHint) {
    return <p className="kb-status-banner is-empty">{emptyHint}</p>;
  }
  return null;
}

export default KbStatusBanner;
