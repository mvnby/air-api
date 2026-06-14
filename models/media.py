from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, String
from sqlmodel import Field, JSON, SQLModel


class MediaAsset(SQLModel, table=True):
    __tablename__ = "media_asset"

    id: Optional[int] = Field(default=None, primary_key=True)
    parent_asset_id: Optional[int] = Field(default=None, foreign_key="media_asset.id", index=True)
    title: str = Field(default="", index=True)
    alt_text: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None, sa_column=Column(String))
    kind: str = Field(default="misc", index=True)
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    variant_type: str = Field(default="original", index=True)
    url: str = Field(index=True)
    original_url: Optional[str] = Field(default=None)
    source_filename: Optional[str] = Field(default=None, index=True)
    mime_type: str = Field(default="image/webp", index=True)
    storage_provider: str = Field(default="local", index=True)
    processing_status: str = Field(default="ready", index=True)
    processing_error: Optional[str] = Field(default=None, sa_column=Column(String))
    content_hash: Optional[str] = Field(default=None, index=True)
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: int = Field(default=0)
    created_by: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)

    def __str__(self) -> str:
        return self.title or self.source_filename or self.url
