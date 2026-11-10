from pydantic import BaseModel


class AmendmentBasisItem(BaseModel):
    document_id: int
    legal_entity_id: int
    number: str
    date: str | None
    status: str
    original_amount: str
    effective_additions: str
    agreed_total: str
    currency: str
    revision: str
    seller_name: str
    customer_name: str
    lines: list[dict[str, str]]


class AmendmentBasisList(BaseModel):
    order_id: int
    items: list[AmendmentBasisItem]
