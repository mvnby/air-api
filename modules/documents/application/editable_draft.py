"""Render and finalize browser-edited DOCX drafts safely.

The editable copy contains already-rendered business data, while official
identity placeholders remain in the DOCX until the explicit issue command.
This keeps Google Drive an editor rather than the numbering source of truth.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from modules.documents.infrastructure.renderers import (
    DocumentTemplateVersion as RenderTemplateVersion,
    NativeDocxRenderer,
    RenderContext,
)

from .artifact_helpers import build_render_inputs


DEFERRED_OFFICIAL_FIELDS = frozenset(
    {
        "document.official_series",
        "document.official_number",
        "document.official_full_number",
        "document.issued_on",
        "document.act_sequence_number",
    }
)


class EditableDraftError(ValueError):
    """The edited DOCX can no longer be issued safely."""


def render_editable_draft(*, template, version, source: bytes, snapshot: dict[str, Any]) -> bytes:
    """Render business data while retaining official fields as placeholders."""
    editable_snapshot = deepcopy(snapshot)
    values = editable_snapshot.setdefault("values", {})
    deferred_fields = _deferred_fields(version.placeholder_schema or {})
    for field in deferred_fields:
        values[field] = _placeholder(field)

    render_template, render_context = build_render_inputs(
        template=template,
        version=version,
        source=source,
        snapshot=editable_snapshot,
    )
    return NativeDocxRenderer().render(render_template, render_context).content


def finalize_editable_draft(
    *,
    source: bytes,
    placeholder_schema: Mapping[str, object],
    official_values: Mapping[str, object],
    required_placeholder_counts: Mapping[str, int] | None = None,
) -> bytes:
    """Validate retained official markers and render the final numbered DOCX."""
    renderer = NativeDocxRenderer()
    expected = validate_editable_draft(
        source=source,
        placeholder_schema=placeholder_schema,
        required_placeholder_counts=required_placeholder_counts,
    )

    values = {
        field: str(official_values.get(field, "") or "")
        for field in expected
    }
    template = RenderTemplateVersion(
        template_key="editable-draft",
        version=1,
        source=source,
        field_catalog=expected,
        filename="editable-draft.docx",
    )
    return renderer.render(
        template,
        RenderContext(values=values, conditions={}, table_rows={}),
    ).content


def validate_editable_draft(
    *,
    source: bytes,
    placeholder_schema: Mapping[str, object],
    required_placeholder_counts: Mapping[str, int] | None = None,
) -> frozenset[str]:
    """Validate a returned DOCX before an official number is reserved."""
    renderer = NativeDocxRenderer()
    allowed = _deferred_fields(placeholder_schema)
    expected_counts = (
        _normalize_required_counts(required_placeholder_counts, allowed)
        if required_placeholder_counts is not None
        else None
    )
    expected = frozenset(expected_counts) if expected_counts is not None else allowed
    discovered_counts = renderer.discover_placeholder_counts(source)
    discovered = frozenset(discovered_counts)
    unknown = discovered - expected
    missing = expected - discovered
    if unknown:
        raise EditableDraftError(
            "Отредактированный документ содержит неизвестные плейсхолдеры: "
            + ", ".join(sorted(unknown))
        )
    if missing:
        raise EditableDraftError(
            "При редактировании удалены служебные поля выпуска: "
            + ", ".join(sorted(missing))
        )
    changed_counts = (
        [
            field
            for field, expected_count in expected_counts.items()
            if discovered_counts.get(field, 0) != expected_count
        ]
        if expected_counts is not None
        else []
    )
    if changed_counts:
        raise EditableDraftError(
            "При редактировании изменено количество служебных полей выпуска: "
            + ", ".join(sorted(changed_counts))
        )
    return expected


def official_placeholder_counts(
    *, source: bytes, placeholder_schema: Mapping[str, object]
) -> dict[str, int]:
    """Capture the exact official-marker contract of the generated draft."""
    allowed = _deferred_fields(placeholder_schema)
    discovered = NativeDocxRenderer().discover_placeholder_counts(source)
    return {
        field: discovered[field]
        for field in sorted(allowed)
        if discovered.get(field, 0) > 0
    }


def preview_values(fields: Iterable[str]) -> dict[str, str]:
    """Human-readable values for a non-authoritative draft preview."""
    return {
        field: (
            "ПРОЕКТ — НОМЕР НЕ ПРИСВОЕН"
            if field in {"document.official_number", "document.official_full_number"}
            else "ПРОЕКТ"
        )
        for field in fields
    }


def _deferred_fields(schema: Mapping[str, object]) -> frozenset[str]:
    raw_fields = schema.get("fields", [])
    if not isinstance(raw_fields, (list, tuple, set, frozenset)):
        raise EditableDraftError("Схема шаблона не содержит корректный каталог полей")
    return frozenset(str(field) for field in raw_fields) & DEFERRED_OFFICIAL_FIELDS


def _normalize_required_counts(
    counts: Mapping[str, int], allowed: frozenset[str]
) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for raw_field, raw_count in counts.items():
        field = str(raw_field)
        if field not in allowed:
            raise EditableDraftError(f"Неизвестное служебное поле выпуска: {field}")
        count = int(raw_count)
        if count < 1:
            raise EditableDraftError(
                f"Некорректное количество служебного поля выпуска: {field}"
            )
        normalized[field] = count
    return normalized


def _placeholder(field: str) -> str:
    return "{{ " + field + " }}"
