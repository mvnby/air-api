"""Version the exact Telegram draft and customer that a manager reviewed."""

import base64
import json
from hashlib import sha256

from models import Customer, CustomerRequisitesRecognition


EDITABLE_FIELDS = frozenset({
    "name", "full_legal_name", "customer_type", "inn", "legal_address",
    "bank_name", "bic", "iban", "email", "phone", "signer_position",
    "signer_name", "acting_basis",
})
TELEGRAM_SOURCES = {"telegram", "telegram_text"}


def review_revision(
    recognition: CustomerRequisitesRecognition, duplicate: Customer | None,
) -> str:
    if recognition.status != "recognized" and recognition.review_revision:
        # An action may itself create or update the duplicate. Keep its accepted
        # revision for idempotent retries even after the customer changes again.
        return recognition.review_revision
    target = None
    if duplicate is not None and recognition.status == "recognized":
        target = {
            field: getattr(duplicate, "type" if field == "customer_type" else field)
            for field in EDITABLE_FIELDS
        }
        target.update(
            id=duplicate.id,
            signing_mode=duplicate.signing_mode,
            is_archived=duplicate.is_archived,
        )
    snapshot = (
        recognition.id, recognition.status, recognition.review_edit_count,
        recognition.extracted_json, recognition.validation_flags, target,
    )
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    # Twelve bytes give a 16-character token that fits in a Telegram callback.
    return base64.urlsafe_b64encode(sha256(encoded.encode()).digest()[:12]).decode()
