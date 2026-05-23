from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class CatalogImportJob(SQLModel, table=True):
    __tablename__ = "catalog_import_job"

    job_id: str = Field(primary_key=True)
    status: str = Field(default="queued", index=True)
    stage: str = Field(default="queued", index=True)
    error: Optional[str] = None

    input_urls: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    with_related: bool = Field(default=False)
    update_existing: bool = Field(default=False)

    input_total: int = Field(default=0)
    total: int = Field(default=0)
    processed: int = Field(default=0)
    pending: int = Field(default=0)
    success_count: int = Field(default=0)
    error_count: int = Field(default=0)
    current_url: Optional[str] = None
    current_title: Optional[str] = None
    successes: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    errors: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )
