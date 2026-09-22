"""One read contract for the visible and derived indoor-unit form factor."""

from sqlalchemy import String, case, cast, func
from sqlalchemy.dialects.postgresql import JSONB

from models import Product
from services.spec_registry import INDOOR_TYPE_LABELS


def _spec_text(session, *path: str):
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        return cast(func.json_extract(Product.specs, "$." + ".".join(path)), String)
    return func.jsonb_extract_path_text(cast(Product.specs, JSONB), *path)


def _canonical_form(raw):
    value = func.replace(func.lower(func.trim(raw)), "ё", "е")
    return case(
        *((value.in_((slug, label)), slug) for slug, label in INDOOR_TYPE_LABELS.items()),
        else_=None,
    )


def indoor_form_factor_expr(session):
    """Prefer the displayed value; retain derived keys for older sparse records."""
    return func.coalesce(
        _canonical_form(_spec_text(session, "indoor_type")),
        _canonical_form(_spec_text(session, "__typed_specs", "indoor_type", "value")),
        _canonical_form(_spec_text(session, "__filter_indoor_type")),
    )
