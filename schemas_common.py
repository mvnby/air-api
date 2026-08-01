"""Small response primitives shared across API schema domains."""

from pydantic import BaseModel


class Meta(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
