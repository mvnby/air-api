"""Presentation constants for Telegram nameplate previews."""

REPAIR_FIELDS = (
    "equipment_name",
    "equipment_brand",
    "equipment_model",
    "equipment_power",
    "equipment_serial_number",
    "equipment_inventory_number",
    "equipment_commissioning_date",
    "refrigerant_type",
    "refrigerant_amount",
)

REPAIR_FIELD_LABELS = {
    "equipment_name": "Оборудование",
    "equipment_brand": "Бренд",
    "equipment_model": "Модель",
    "equipment_power": "Мощность",
    "equipment_serial_number": "Серийный номер",
    "equipment_inventory_number": "Инвентарный номер",
    "equipment_commissioning_date": "Дата ввода",
    "refrigerant_type": "Хладагент",
    "refrigerant_amount": "Количество хладагента",
}

WARRANTY_UNIT_TYPES = {"indoor_unit", "outdoor_unit"}
WARRANTY_FIELD_LABELS = {
    "brand": "Бренд",
    "model": "Модель блока",
    "serial": "Серийный номер",
    "refrigerant_type": "Хладагент",
}
WARRANTY_UNIT_LABELS = {
    "indoor_unit": "внутренний блок",
    "outdoor_unit": "наружный блок",
}
