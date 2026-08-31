from __future__ import annotations

from dataclasses import dataclass


DEFAULT_GOODS_WARRANTY_MONTHS = 36
B2C_NATIVE_DOCUMENT_TYPES = frozenset(
    {
        "b2c_supply_installation_act",
        "b2c_customer_equipment_installation_act",
        "b2c_maintenance_repair_act",
        "b2c_route_laying_act",
    }
)


@dataclass(frozen=True, slots=True)
class ConsumerDocumentTerms:
    """Typed B2C facts captured into a document's immutable render snapshot."""

    equipment_brand: str | None = None
    equipment_model: str | None = None
    equipment_serial: str | None = None
    goods_warranty_months: int | None = None
    goods_warranty_terms: str | None = None
    work_warranty_months: int | None = None
    work_warranty_terms: str | None = None
    route_length_meters: str | None = None
    route_liquid_pipe_diameter_mm: str | None = None
    route_gas_pipe_diameter_mm: str | None = None
    route_drainage: str | None = None
    route_power_supply: str | None = None
    route_notes: str | None = None
    route_photo_fixation_performed: bool = False
    route_pressure_test_performed: bool = False
    route_ends_capped: bool = False
