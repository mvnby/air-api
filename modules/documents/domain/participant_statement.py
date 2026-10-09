"""Manager supplied facts; this type never infers legal certifications."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParticipantStatement:
    procedure_reference: str
    lot: str
    buyer_name: str
    declaration_text: str

    def values(self) -> dict[str, str]:
        fields = {
            "procedure_reference": self.procedure_reference,
            "lot": self.lot,
            "buyer_name": self.buyer_name,
            "declaration_text": self.declaration_text,
        }
        normalized = {name: str(value or "").strip() for name, value in fields.items()}
        for name, label in (("procedure_reference", "процедуру закупки"), ("lot", "лот"),
                            ("buyer_name", "заказчика закупки"), ("declaration_text", "текст заявления")):
            if not normalized[name]:
                raise ValueError(f"Для заявления участника заполните {label}")
        limits = {"procedure_reference": 1000, "lot": 500, "buyer_name": 500, "declaration_text": 20000}
        if any(len(value) > limits[name] for name, value in normalized.items()):
            raise ValueError("Реквизиты заявления участника превышают допустимую длину")
        return {f"participant.{name}": value for name, value in normalized.items()}
