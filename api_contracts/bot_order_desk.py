"""Scoped order workspace shared with the autonomous Telegram runtime."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from api_contracts.bot_order_followup import BotOrderFollowup, BotOrderFollowupChange
from api_contracts.bot_order_proposal import BotOrderProposals, BotProposalChange
from api_contracts.bot_workspace import BotWorkspaceActor


BotOrderRevision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]
DocumentType = Literal["offer", "invoice"]


class BotOrderDocument(BaseModel):
    id: int
    title: str
    status: str
    proposal_id: int | None
    url: HttpUrl | None
    can_preview: bool


class BotOrderIssuer(BaseModel):
    id: int
    name: str
    types: list[DocumentType]


class BotOrderDesk(BotOrderProposals):
    id: int
    title: str
    status: str
    status_label: str
    currency: Literal["BYN"]
    revision: BotOrderRevision
    manager_url: HttpUrl
    followup: BotOrderFollowup
    documents: list[BotOrderDocument]
    document_issuers: list[BotOrderIssuer]


class BotOrderPrepareDocument(BaseModel, extra="forbid"):
    kind: Literal["prepare_document"]
    document_type: DocumentType
    legal_entity_id: int = Field(gt=0, strict=True)
    proposal_id: Annotated[int, Field(gt=0, strict=True)] | None


class BotOrderCommand(BaseModel, extra="forbid"):
    expected_revision: BotOrderRevision
    idempotency_key: UUID
    change: Annotated[BotOrderFollowupChange | BotProposalChange | BotOrderPrepareDocument, Field(discriminator="kind")]


class BotOrderCommandRequest(BotOrderCommand, BotWorkspaceActor):
    pass


class BotOrderQuote(BaseModel):
    text: str
