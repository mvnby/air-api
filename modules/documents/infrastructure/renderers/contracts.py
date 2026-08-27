"""Stable, provider-neutral inputs and outputs for document renderers.

These types deliberately contain no ORM objects. The application layer is
responsible for producing a frozen snapshot before any renderer is called.
That makes a renderer safe to run in-process today and in a worker/service
later without changing its contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
from types import MappingProxyType
from typing import Any, Mapping


_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\Z")


def _freeze_text_mapping(values: Mapping[str, Any], *, label: str) -> Mapping[str, str]:
    frozen: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be non-empty strings")
        if value is None:
            frozen[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            frozen[key] = str(value)
        else:
            raise TypeError(f"{label}[{key!r}] must be a scalar value")
    return MappingProxyType(frozen)


def _freeze_bool_mapping(values: Mapping[str, bool]) -> Mapping[str, bool]:
    frozen: dict[str, bool] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key:
            raise ValueError("conditions keys must be non-empty strings")
        if not _IDENTIFIER_PATTERN.fullmatch(key):
            raise ValueError(f"condition name {key!r} must be a safe identifier")
        if not isinstance(value, bool):
            raise TypeError(f"conditions[{key!r}] must be a bool")
        frozen[key] = value
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class TableBlockSpec:
    """A repeatable DOCX table row declared by an anchor such as ``{{ lines }}``."""

    name: str
    row_fields: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_fields", frozenset(self.row_fields))
        if not self.name or "." in self.name:
            raise ValueError("table block name must be a simple placeholder name")
        if not self.row_fields:
            raise ValueError("table block must declare at least one row field")


@dataclass(frozen=True, slots=True)
class DocumentTemplateVersion:
    """An immutable template revision and its approved placeholder catalogue."""

    template_key: str
    version: int
    source: bytes
    field_catalog: frozenset[str]
    table_blocks: tuple[TableBlockSpec, ...] = ()
    filename: str = "template.docx"
    condition_catalog: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_catalog", frozenset(self.field_catalog))
        object.__setattr__(self, "table_blocks", tuple(self.table_blocks))
        object.__setattr__(self, "condition_catalog", frozenset(self.condition_catalog))
        if not self.template_key:
            raise ValueError("template_key is required")
        if self.version < 1:
            raise ValueError("template version must be positive")
        if not isinstance(self.source, bytes) or not self.source:
            raise ValueError("template source must be a non-empty DOCX byte string")
        if not self.filename.lower().endswith(".docx"):
            raise ValueError("template filename must use the .docx extension")
        invalid_conditions = [
            name
            for name in self.condition_catalog
            if not isinstance(name, str) or not _IDENTIFIER_PATTERN.fullmatch(name)
        ]
        if invalid_conditions:
            raise ValueError(
                "condition catalog contains unsafe identifiers: "
                f"{sorted(map(repr, invalid_conditions))}"
            )

        names = [block.name for block in self.table_blocks]
        if len(names) != len(set(names)):
            raise ValueError("table block names must be unique")
        row_fields = [
            field for block in self.table_blocks for field in block.row_fields
        ]
        if len(row_fields) != len(set(row_fields)):
            raise ValueError("row fields cannot belong to more than one table block")
        reserved = set(names) | set(row_fields)
        overlap = reserved & set(self.field_catalog)
        if overlap:
            raise ValueError(
                f"field catalog contains reserved table placeholders: {sorted(overlap)}"
            )

    @property
    def content_sha256(self) -> str:
        return sha256(self.source).hexdigest()


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Frozen values and rows captured from the CRM before rendering starts."""

    values: Mapping[str, str]
    table_rows: Mapping[str, tuple[Mapping[str, str], ...]] = field(
        default_factory=dict
    )
    conditions: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = _freeze_text_mapping(self.values, label="values")
        rows: dict[str, tuple[Mapping[str, str], ...]] = {}
        for table_name, table_rows in self.table_rows.items():
            if not isinstance(table_name, str) or not table_name:
                raise ValueError("table row keys must be non-empty strings")
            rows[table_name] = tuple(
                _freeze_text_mapping(row, label=f"table_rows[{table_name!r}]")
                for row in table_rows
            )
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "table_rows", MappingProxyType(rows))
        object.__setattr__(self, "conditions", _freeze_bool_mapping(self.conditions))


@dataclass(frozen=True, slots=True)
class TemplateValidationIssue:
    code: str
    message: str
    location: str
    placeholder: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateValidationResult:
    issues: tuple[TemplateValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.issues


class TemplateValidationError(ValueError):
    """Raised before rendering when a template or context violates the contract."""

    def __init__(self, result: TemplateValidationResult):
        self.result = result
        message = (
            "; ".join(issue.message for issue in result.issues)
            or "template validation failed"
        )
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RenderedDocx:
    content: bytes
    template_key: str
    template_version: int
    content_sha256: str
    media_type: str = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def make_rendered_docx(
    content: bytes, template: DocumentTemplateVersion
) -> RenderedDocx:
    return RenderedDocx(
        content=content,
        template_key=template.template_key,
        template_version=template.version,
        content_sha256=sha256(content).hexdigest(),
    )
