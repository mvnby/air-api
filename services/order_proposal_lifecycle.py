from __future__ import annotations

from datetime import datetime
from typing import Optional

from models import Order, OrderProposal


PROPOSAL_STATUS_DRAFT = "draft"
PROPOSAL_STATUS_READY = "ready_to_send"
PROPOSAL_STATUS_SENT = "sent"
PROPOSAL_STATUS_APPROVED = "approved"
PROPOSAL_STATUS_REJECTED = "rejected"

PROPOSAL_STATUSES = {
    PROPOSAL_STATUS_DRAFT,
    PROPOSAL_STATUS_READY,
    PROPOSAL_STATUS_SENT,
    PROPOSAL_STATUS_APPROVED,
    PROPOSAL_STATUS_REJECTED,
}


def normalize_proposal_status(value: Optional[str]) -> str:
    status = str(value or PROPOSAL_STATUS_DRAFT).strip().lower()
    if status == "accepted":
        status = PROPOSAL_STATUS_APPROVED
    if status not in PROPOSAL_STATUSES:
        raise ValueError(f"Unsupported proposal status: {status}")
    return status


def sync_selected_proposal_status(
    order: Order,
    proposal: OrderProposal,
    *,
    now: Optional[datetime] = None,
) -> None:
    """Keep the order summary in sync without conflating both entities."""
    if not proposal.is_selected:
        return

    changed_at = now or datetime.now()
    status = normalize_proposal_status(proposal.status)
    order.proposal_status = status

    if status == PROPOSAL_STATUS_SENT:
        order.proposal_sent_at = changed_at
        order.negotiation_status = "proposal_sent"
        order.negotiation_status_changed_at = changed_at
    elif status == PROPOSAL_STATUS_APPROVED:
        order.negotiation_status = "awaiting_payment"
        order.negotiation_status_changed_at = changed_at
    elif status == PROPOSAL_STATUS_REJECTED:
        order.negotiation_status = "follow_up"
        order.negotiation_status_changed_at = changed_at
    elif order.negotiation_status in {"proposal_sent", "awaiting_payment"}:
        order.negotiation_status = "awaiting_offer"
        order.negotiation_status_changed_at = changed_at
