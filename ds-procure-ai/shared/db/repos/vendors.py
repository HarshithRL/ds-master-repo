"""Vendor (bid) selection state."""

from __future__ import annotations

from shared.db.connection import session_scope
from shared.db.models import Vendor, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__)

SHORTLISTED = "shortlisted"
BIDDER = "bidder"


def vendor_row_id(project_id: str, bid_id: str) -> str:
    """Vendor rows are keyed f"{project_id}:{bid_id}" by the extraction pipeline."""
    return f"{project_id}:{bid_id}"


def set_shortlisted(project_id: str, bid_id: str, shortlisted: bool) -> None:
    row_id = vendor_row_id(project_id, bid_id)
    status = SHORTLISTED if shortlisted else BIDDER
    with session_scope() as session:
        vendor = session.get(Vendor, row_id)
        if vendor is None:
            # Bid exists in evidence but has no vendor row yet (extraction may
            # not have emitted one); create it so the tick still persists.
            session.add(
                Vendor(
                    id=row_id,
                    project_id=project_id,
                    name=bid_id,
                    status=status,
                    created_at=utc_now_iso(),
                )
            )
            log.info("vendor row created for shortlist project_id={} bid_id={}", project_id, bid_id)
            return
        vendor.status = status
