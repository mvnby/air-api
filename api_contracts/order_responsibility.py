"""Company-local order responsibility, separate from installation assignments."""

from pydantic import BaseModel, ConfigDict, Field


class ManagerOrderResponsiblePerson(BaseModel):
    staff_user_id: int
    display_name: str
    avatar_url: str | None = None
    is_active: bool


class ManagerOrderResponsiblesResponse(BaseModel):
    items: list[ManagerOrderResponsiblePerson]
    total: int
    page: int
    limit: int


class ManagerOrderResponsibleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsible_staff_user_id: int | None = Field(ge=1)
    expected_version: int = Field(ge=0)
