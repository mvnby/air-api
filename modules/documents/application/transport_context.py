from __future__ import annotations

from dataclasses import dataclass

from modules.documents.domain import TransportTerms


@dataclass(frozen=True, slots=True)
class TransportDocumentContext:
    values: dict[str, str]


def build_transport_document_context(
    terms: TransportTerms | None,
) -> TransportDocumentContext:
    resolved = terms or TransportTerms()
    return TransportDocumentContext(
        values={
            "transport.car_model": _value(resolved.car_model),
            "transport.car_number": _value(resolved.car_number),
            "transport.driver_name": _value(resolved.driver_name),
            "transport.carrier": _value(resolved.carrier),
        }
    )


def _value(value: object) -> str:
    return str(value or "").strip() or "—"

