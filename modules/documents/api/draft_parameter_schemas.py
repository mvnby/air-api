from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import ConsumerDocumentTermsPayload, TransportTermsPayload
from .business_schemas import ActTermsPayload, BusinessDocumentTermsPayload
from modules.documents.domain.repair_defect import RepairDefect
from .participant_statement_schemas import ParticipantStatementPayload


class ManagedDocumentDraftParameters(BaseModel):
    issue_date: date
    issue_city: str | None = None
    business_terms: BusinessDocumentTermsPayload | None = None
    consumer_terms: ConsumerDocumentTermsPayload | None = None
    act_terms: ActTermsPayload | None = None
    transport_terms: TransportTermsPayload | None = None
    repair_defect: RepairDefect | None = None
    participant_statement: ParticipantStatementPayload | None = None
    revision: str
    template_version_id: int
    has_editable_copy: bool
    total_amount: str
    order_conditions: str | None = None


class ManagedDocumentDraftParameterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: str = Field(pattern="^[a-f0-9]{64}$")
    reset_editable_copy: bool = False
    template_version_id: int | None = Field(default=None, gt=0)
    issue_date: date | None = None
    issue_city: str | None = Field(default=None, max_length=160)
    business_terms: BusinessDocumentTermsPayload | None = None
    consumer_terms: ConsumerDocumentTermsPayload | None = None
    act_terms: ActTermsPayload | None = None
    transport_terms: TransportTermsPayload | None = None
    repair_defect: RepairDefect | None = None
    participant_statement: ParticipantStatementPayload | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if self.template_version_id is not None and self.model_fields_set - {
            "template_version_id",
            "expected_revision",
            "reset_editable_copy",
        }:
            raise ValueError(
                "Примените версию шаблона отдельно от изменения параметров"
            )
        for name in self.model_fields_set - {
            "expected_revision",
            "reset_editable_copy",
            "issue_city",
        }:
            if getattr(self, name) is None:
                raise ValueError("Параметры черновика нельзя очистить целиком")
        return self
