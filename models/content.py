from datetime import datetime
from typing import Any, Optional

from sqlmodel import Field, SQLModel


class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    slug: str = Field(unique=True, index=True)
    content: str
    main_image: Optional[str] = None
    cover_image: Optional[str] = None
    is_published: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def main_image_file(self) -> Any:
        return getattr(self, "_temp_main_image_file", None)

    @main_image_file.setter
    def main_image_file(self, value: Any):
        self._temp_main_image_file = value

    @property
    def cover_image_file(self) -> Any:
        return getattr(self, "_temp_cover_image_file", None)

    @cover_image_file.setter
    def cover_image_file(self, value: Any):
        self._temp_cover_image_file = value

    def __str__(self):
        return self.title


class GlobalConfig(SQLModel, table=True):
    __tablename__ = "global_config"
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.now)

    def __str__(self):
        return f"{self.key}: {self.value}"
