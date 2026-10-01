"""Read the Manager's quick service-only choices from the published price book."""
from schemas_installation_confirmation import ManagerInstallationStandardTariff, ManagerInstallationStandardTariffList
from schemas_installation_price_book import InstallationMatcher


async def list_standard_tariffs(session, scope) -> ManagerInstallationStandardTariffList:
    from services.installation_price_book_service import InstallationPriceBookService as Book
    book = await Book.latest(session, scope)
    items = []
    for entry in book.entries if book else []:
        match = InstallationMatcher.model_validate(entry["match"])
        if entry["mode"] != "fixed" or match.work_kind != "standard" or \
           match.product_kind != "complete_split_system" or match.match_strategy not in {"capacity_only", "type_only"}:
            continue
        items.append(ManagerInstallationStandardTariff(code=entry["code"],
            title=Book.short_title(entry), description=Book.standard_description(entry),
            price=entry["base_price"], product_kind=match.product_kind, indoor_type=match.indoor_type,
            route_m=entry["included_route_m"], holes_by_type=entry["included_holes"]))
    return ManagerInstallationStandardTariffList(price_book_revision=book.revision if book else None, items=items)
