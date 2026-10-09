from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParticipantStatementPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    procedure_reference: str = Field(min_length=1, max_length=1000)
    lot: str = Field(min_length=1, max_length=500)
    buyer_name: str = Field(min_length=1, max_length=500)
    declaration_text: str = Field(min_length=1, max_length=20000)

    @field_validator("procedure_reference", "lot", "buyer_name", "declaration_text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Заполните реквизиты и текст заявления участника")
        return value
