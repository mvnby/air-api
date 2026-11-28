"""Proposal and commercial line commands for the Telegram order desk."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api_contracts.bot_shop_actions import BotShopBasket, BotShopLine


_Id = Annotated[int, Field(gt=0, strict=True)]
_Quantity = Annotated[int, Field(ge=1, le=99, strict=True)]
_Price = Annotated[Decimal, Field(ge=0, le=2_147_483_647, decimal_places=2)]


class BotOrderSelectProposal(BaseModel, extra="forbid"):
    kind: Literal["select_proposal"]
    proposal_id: _Id


class BotOrderUpdateLine(BaseModel, extra="forbid"):
    kind: Literal["update_proposal_line"]
    proposal_id: _Id | None
    line_kind: Literal["product", "service"]
    line_id: _Id
    quantity: _Quantity | None = None
    unit_price: _Price | None = None

    @model_validator(mode="after")
    def validate_change(self):
        if self.quantity is None and self.unit_price is None:
            raise ValueError("Укажите количество или цену позиции")
        if self.line_kind == "product" and self.unit_price is not None and self.unit_price % 1:
            raise ValueError("Цена оборудования указывается в целых рублях")
        return self


class BotOrderRemoveLine(BaseModel, extra="forbid"):
    kind: Literal["remove_proposal_line"]
    proposal_id: _Id | None
    line_kind: Literal["product", "service"]
    line_id: _Id
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Подтвердите удаление позиции")
        return value


class BotOrderEquipmentLine(BotShopLine):
    expected_unit_price_byn: int = Field(gt=0, le=2_147_483_647)


class BotOrderAddEquipment(BotShopBasket):
    kind: Literal["add_equipment"]
    proposal_id: _Id | None
    items: list[BotOrderEquipmentLine] = Field(min_length=1, max_length=30)


class BotOrderAddInstallation(BaseModel, extra="forbid"):
    kind: Literal["add_installation"]
    proposal_id: _Id | None
    option_id: str = Field(min_length=1, max_length=160)
    quantity: _Quantity


BotProposalChange = (
    BotOrderSelectProposal | BotOrderUpdateLine | BotOrderRemoveLine | BotOrderAddEquipment | BotOrderAddInstallation
)


class BotOrderProposalDisplayLine(BaseModel):
    title: str
    description: str | None = None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class BotOrderProposalLine(BotOrderProposalDisplayLine):
    id: int
    can_edit_quantity: bool
    can_edit_price: bool
    can_remove: bool = False


class BotOrderProposalProduct(BotOrderProposalLine):
    product_id: int | None
    is_installation_included: bool


class BotOrderProposalService(BotOrderProposalLine):
    service_id: int | None
    unit: str | None
    display_lines: list[BotOrderProposalDisplayLine] = Field(default_factory=list)


class BotOrderInstallationOption(BaseModel):
    id: str
    title: str
    description: str | None
    unit_price: Decimal


class BotOrderProposal(BaseModel):
    id: int | None
    name: str
    status: str
    is_selected: bool
    is_archived: bool
    total_amount: Decimal
    equipment_total: Decimal
    services_total: Decimal
    can_select: bool
    can_add_equipment: bool
    product_lines: list[BotOrderProposalProduct]
    service_lines: list[BotOrderProposalService]
    installation_options: list[BotOrderInstallationOption]


class BotOrderProposals(BaseModel):
    proposals: list[BotOrderProposal]
    selected_proposal_id: int | None
