"""Read-only Manager service templates from the tenant's published price book."""
from decimal import Decimal

from schemas_installation_confirmation import (
    ManagerInstallationStandardSuggestion,
    ManagerInstallationStandardSuggestionsResponse,
    ManagerInstallationStandardTariff,
    ManagerInstallationStandardTariffList,
)
from schemas_installation_price_book import InstallationMatcher
from services.product_collection_catalog_access import ProductCollectionCatalogAccess


_TYPE_LABELS = {
    "wall": "настенного", "cassette": "кассетного", "duct": "канального",
    "floor_ceiling": "напольно-потолочного", "column": "колонного", "console": "консольного",
}


def standard_entries(book):
    """Only approved basic fixed standards are safe to offer as editable CP rows."""
    entries = []
    for entry in book.entries if book else []:
        match = InstallationMatcher.model_validate(entry["match"])
        if entry["mode"] == "fixed" and match.work_kind == "standard" and \
           match.product_kind == "complete_split_system" and match.match_strategy in {"capacity_only", "type_only"}:
            entries.append((entry, match))
    return sorted(entries, key=lambda pair: (
        0 if pair[1].indoor_type == "wall" else 1,
        pair[1].indoor_type or "",
        pair[1].capacity_min_kw or Decimal("0"),
        pair[1].capacity_max_kw or Decimal("Infinity"),
        pair[0]["code"],
    ))


def project_standard_tariff(entry, match) -> ManagerInstallationStandardTariff:
    from services.installation_price_book_service import InstallationPriceBookService as Book
    title = f"Стандартный монтаж {_TYPE_LABELS[match.indoor_type]} кондиционера"
    minimum, maximum = match.capacity_min_kw, match.capacity_max_kw
    if minimum is not None:
        title += f" {'от' if match.capacity_min_inclusive else 'свыше'} {Book._quantity_text(minimum)}"
    if maximum is not None:
        upper_label = "до" if match.capacity_max_inclusive else ("и менее" if minimum is not None else "менее")
        title += f" {upper_label} {Book._quantity_text(maximum)}"
    if minimum is not None or maximum is not None:
        title += " кВт"
    return ManagerInstallationStandardTariff(
        code=entry["code"], title=title, description=Book.standard_description(entry),
        price=entry["base_price"], product_kind=match.product_kind, indoor_type=match.indoor_type,
        route_m=entry["included_route_m"], holes_by_type=entry["included_holes"],
        capacity_min_kw=minimum, capacity_max_kw=maximum,
        capacity_min_inclusive=match.capacity_min_inclusive if minimum is not None else None,
        capacity_max_inclusive=match.capacity_max_inclusive if maximum is not None else None,
    )


async def list_standard_tariffs(session, scope) -> ManagerInstallationStandardTariffList:
    from services.installation_price_book_service import InstallationPriceBookService as Book
    book = await Book.latest(session, scope)
    return ManagerInstallationStandardTariffList(
        price_book_revision=book.revision if book else None,
        items=[project_standard_tariff(entry, match) for entry, match in standard_entries(book)],
    )


async def suggest_standard_tariffs(session, scope, product_ids) -> ManagerInstallationStandardSuggestionsResponse:
    from services.installation_price_book_service import InstallationPriceBookService as Book
    book = await Book.latest(session, scope)
    entries = standard_entries(book)
    if not entries or not product_ids:
        return ManagerInstallationStandardSuggestionsResponse()
    visible = await ProductCollectionCatalogAccess.visible_by_ids(
        session, tenant_scope=scope, product_ids=product_ids,
    )
    items = []
    for product_id in dict.fromkeys(product_ids):
        projection = visible.get(product_id)
        if projection is None:
            continue
        try:
            profile, _ = Book._product_profile(projection.product, basic_only=True)
        except ValueError:
            continue
        if profile is None or profile.product_kind != "complete_split_system" or \
           profile.indoor_type is None or profile.capacity_cooling_kw is None:
            continue
        candidates = [(entry, match) for entry, match in entries if Book._match(profile, entry)[0]]
        if len(candidates) != 1:
            continue
        entry, match = candidates[0]
        items.append(ManagerInstallationStandardSuggestion(
            product_id=product_id, tariff=project_standard_tariff(entry, match),
        ))
    return ManagerInstallationStandardSuggestionsResponse(items=items)
