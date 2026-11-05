from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.documents.domain import TransportTerms
from modules.documents.domain.transport_terms import TransportOperation


@dataclass(frozen=True, slots=True)
class TransportDocumentContext:
    values: dict[str, str]


def build_transport_document_context(
    terms: TransportTerms | None,
    *,
    document_type: str,
) -> TransportDocumentContext:
    resolved = terms or TransportTerms()
    # Keep the historic display of the four shared fields in existing templates.
    values = {
        f"transport.{name}": str(getattr(resolved, name) or "").strip() or "—"
        for name in ("car_model", "car_number", "driver_name", "carrier")
    }
    route_fields = (
        "trip_sheet_number",
        "freight_payer",
        "freight_payer_unp",
        "loading_point",
        "unloading_point",
    )
    if document_type != "ttn1":
        if (
            resolved.loading
            or resolved.unloading
            or any(getattr(resolved, name) for name in route_fields)
        ):
            raise ValueError(
                "Маршрут и погрузочно-разгрузочные операции доступны только для ТТН-1"
            )
        return TransportDocumentContext(values=values)

    route = {
        f"transport.{name}": str(getattr(resolved, name) or "").strip()
        for name in route_fields
    }
    for stage in ("loading", "unloading"):
        operation = getattr(resolved, stage) or TransportOperation()
        for name in ("performer", "method"):
            route[f"transport.{stage}.{name}"] = getattr(operation, name) or ""
        for name in ("arrived_at", "departed_at"):
            local_time = getattr(operation, name)
            route[f"transport.{stage}.{name}"] = (
                datetime.fromisoformat(local_time).strftime("%d.%m.%Y %H:%M")
                if local_time
                else ""
            )
        minutes = operation.downtime_minutes
        route[f"transport.{stage}.downtime"] = (
            f"{minutes // 60}:{minutes % 60:02d}" if minutes is not None else ""
        )
    values.update(route)
    return TransportDocumentContext(values=values)
