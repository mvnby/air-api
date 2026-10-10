"""Editable draft facts, projected from the saved context rather than live CRM data."""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json

from modules.documents.domain import (
    B2C_NATIVE_DOCUMENT_TYPES,
    BUSINESS_TERMS_DOCUMENT_TYPES,
)

BUSINESS_FIELDS = {
    "contract_scenario": "contract.scenario",
    "subject": "contract.subject",
    "delivery_deadline": "contract.delivery_deadline",
    "performance_deadline": "contract.performance_deadline",
    "valid_until": "contract.valid_until",
    "additional_conditions": "contract.additional_conditions",
    "goods_warranty_months": "warranty.goods.months",
    "goods_warranty_terms": "warranty.goods.terms",
    "work_warranty_months": "warranty.work.months",
    "work_warranty_terms": "warranty.work.terms",
}
CONSUMER_FIELDS = {
    "equipment_brand": "equipment.brand",
    "equipment_model": "equipment.model",
    "equipment_serial": "equipment.serial",
    "goods_warranty_months": "warranty.goods.months",
    "goods_warranty_terms": "warranty.goods.terms",
    "work_warranty_months": "warranty.work.months",
    "work_warranty_terms": "warranty.work.terms",
    "route_length_meters": "route.length_meters",
    "route_liquid_pipe_diameter_mm": "route.liquid_pipe_diameter_mm",
    "route_gas_pipe_diameter_mm": "route.gas_pipe_diameter_mm",
    "route_drainage": "route.drainage",
    "route_power_supply": "route.power_supply",
    "route_notes": "route.notes",
    "installation_first_stage_amount": "installation.first_stage_amount",
}
ACT_FIELDS = {
    name: f"act.{name}"
    for name in ("result_text", "claims_text", "acceptance_deadline")
}
TRANSPORT_FIELDS = {
    name: f"transport.{name}"
    for name in ("car_model", "car_number", "driver_name", "carrier")
}
PARTICIPANT_FIELDS = {
    name: f"participant.{name}"
    for name in ("procedure_reference", "lot", "buyer_name", "declaration_text")
}
TERM_GROUPS = (
    "business_terms",
    "consumer_terms",
    "act_terms",
    "transport_terms",
    "participant_statement",
)


def json_terms(terms):
    return (
        json.loads(json.dumps(asdict(terms), default=str))
        if terms is not None
        else None
    )


def draft_revision(document, artifacts=()) -> str:
    return sha256(
        json.dumps(
            {
                "snapshot": document.render_snapshot,
                "date": document.date.isoformat(),
                "template_version_id": document.template_version_id,
                "sources": sorted(
                    (item.id, item.checksum_sha256, item.is_authoritative)
                    for item in artifacts
                ),
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def _fields(values, mapping):
    result = {}
    for name, key in mapping.items():
        value = values.get(key) or None
        if value == "—":
            value = None
        if value is not None and name.endswith("_months"):
            value = int(value)
        if value is not None and name.endswith(("_deadline", "_until")):
            value = datetime.strptime(value, "%d.%m.%Y").date().isoformat()
        result[name] = value
    return result


def _schedule(snapshot):
    events = {
        "до поставки": "before_supply",
        "до начала работ": "before_work",
        "после поставки": "after_supply",
        "после выполнения работ": "after_work",
        "после приемки": "after_acceptance",
    }
    days = {"календар": "calendar", "банковск": "banking", "рабоч": "working"}
    result = []
    for row in snapshot.get("table_rows", {}).get("payment_schedule", []):
        label = row.get("payment.due_event", "")
        event = next((value for key, value in events.items() if key in label), None)
        if event is None:
            raise ValueError("Не удалось прочитать сохранённый график оплаты")
        result.append(
            {
                "share_percent": row["payment.share_percent"],
                "due_event": event,
                "due_days": (
                    int(row["payment.due_days"])
                    if row.get("payment.due_days")
                    else None
                ),
                "due_day_kind": next(
                    (
                        value
                        for key, value in days.items()
                        if key in row.get("payment.due_day_kind", "")
                    ),
                    "calendar",
                ),
                "note": row.get("payment.note") or None,
            }
        )
    return result


def read_draft_parameters(document) -> dict:
    """Legacy drafts recover exact saved terms; new drafts also retain typed source facts."""
    snapshot = document.render_snapshot or {}
    values, conditions = snapshot.get("values", {}), snapshot.get("conditions", {})
    saved = deepcopy(snapshot.get("meta", {}).get("draft_parameters", {}))
    result = {
        "issue_date": document.date.date().isoformat(),
        "issue_city": values.get("document.issue_city") or None,
        **dict.fromkeys(TERM_GROUPS),
    }
    if document.doc_type in BUSINESS_TERMS_DOCUMENT_TYPES:
        terms = _fields(values, BUSINESS_FIELDS)
        terms.update(
            additional_conditions_overridden=True, payment_schedule=_schedule(snapshot)
        )
        result["business_terms"] = saved.get("business_terms") or terms
    if document.doc_type in B2C_NATIVE_DOCUMENT_TYPES:
        terms = _fields(values, CONSUMER_FIELDS)
        for name in (
            "route_photo_fixation_performed",
            "route_pressure_test_performed",
            "route_ends_capped",
        ):
            terms[name] = bool(conditions.get(name.replace("route_", "route.", 1)))
        terms["installation_two_stages"] = bool(
            conditions.get("installation.two_stages")
        )
        terms["installation_outdoor_unit_in_first_stage"] = (
            "Установка наружного блока"
            in values.get("installation.first_stage_works", "")
            or not terms["installation_two_stages"]
        )
        result["consumer_terms"] = saved.get("consumer_terms") or terms
        for name in ("goods_warranty_months", "work_warranty_months"):
            if result["consumer_terms"].get(name) is None:
                result["consumer_terms"][name] = terms[name]
    if document.doc_type == "act":
        result["act_terms"] = saved.get("act_terms") or {
            **_fields(values, ACT_FIELDS),
            "claims_status": (
                "present" if conditions.get("act.claims_present") else "none"
            ),
        }
    if document.doc_type in {"tn2", "ttn1"}:
        result["transport_terms"] = saved.get("transport_terms") or _fields(
            values, TRANSPORT_FIELDS
        )
    if document.doc_type == "participant_statement":
        result["participant_statement"] = saved.get("participant_statement") or _fields(
            values, PARTICIPANT_FIELDS
        )
    return result


def saved_total(snapshot) -> Decimal:
    return Decimal(str(snapshot.get("values", {}).get("totals.amount") or "0"))
