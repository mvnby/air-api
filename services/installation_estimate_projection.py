"""Grouped commercial lines derived only from an accepted installation snapshot."""
from decimal import Decimal
import json

from schemas_installation_confirmation import ManagerInstallationPreviewLine
from schemas_installation_price_book import InstallationPreviewResponse


def grouped_installation_lines(result: InstallationPreviewResponse, *, include_policy_notes: bool = True) -> list[ManagerInstallationPreviewLine]:
    groups: dict[str, ManagerInstallationPreviewLine] = {}
    for summary in result.installations:
        parts = [part for part in result.components if part.installation_key == summary.installation_key]
        amount = sum((part.net for part in parts), Decimal("0.00"))
        measured = sorted(({**item.model_dump(mode="json"),
            **{field: format(getattr(item, field).normalize(), "f") for field in ("actual", "included", "extra")}}
            for item in summary.measured if item.actual > 0),
                          key=lambda item: item["code"])
        extras = sorted(({**item.model_dump(mode="json"), "quantity": format(item.quantity.normalize(), "f")}
                         for item in summary.selected_extras),
                        key=lambda item: item["code"])
        signature = json.dumps({"tariff": summary.tariff_code, "measured": measured,
            "extras": extras, "scope": summary.included_scope, "amount": str(amount.quantize(Decimal("0.01")))}, sort_keys=True)
        if signature in groups:
            groups[signature].quantity += 1
            continue
        details = list(summary.included_scope)
        for item in summary.measured:
            if item.actual > 0:
                actual = format(item.actual.normalize(), "f").replace(".", ",")
                included = format(item.included.normalize(), "f").replace(".", ",")
                details.append(f"{item.label}: {actual} {item.unit} (включено {included} {item.unit})")
        for item in summary.selected_extras:
            details.append(f"{item.label}: {item.quantity.normalize():f} {item.unit}")
        selected_codes = {item.code for item in summary.selected_extras}
        exclusions = []
        if not any(code.startswith("pump.") for code in selected_codes):
            exclusions.append("дренажный насос")
        site_codes = {item.code for item in result.site_work}
        if "access.lift" not in site_codes:
            exclusions.append("вышка")
        if "access.scaffold" not in site_codes:
            exclusions.append("леса")
        if exclusions and include_policy_notes:
            details.append("Не включены: " + ", ".join(exclusions))
        if include_policy_notes:
            details.append("Новая линия от щита и отдельная розетка — по согласованию")
        if include_policy_notes and not any(item.code == "route.length_m" and item.extra > 0 for item in summary.measured):
            details.append("Дополнительная трасса не включена")
        groups[signature] = ManagerInstallationPreviewLine(
            title=summary.short_title or summary.work_label, description="; ".join(details), price=amount)
    lines = list(groups.values())
    for part in result.components:
        if part.installation_key is None:
            lines.append(ManagerInstallationPreviewLine(title=part.description, price=part.net))
    if sum((line.price * line.quantity for line in lines), Decimal("0.00")) != result.total:
        raise ValueError("Grouped installation totals do not reconcile")
    return lines


async def frozen_installation_presentations(session, links) -> dict[int, dict]:
    """Read accepted composition without changing historical titles, quantities or prices."""
    from sqlmodel import select
    from models import InstallationEstimateRevision, InstallationEstimate
    from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService
    ids = {link.installation_estimate_revision_id for link in links if link.installation_estimate_revision_id}
    if not ids:
        return {}
    revisions = (await session.execute(select(InstallationEstimateRevision, InstallationEstimate)
        .join(InstallationEstimate, InstallationEstimate.id == InstallationEstimateRevision.estimate_id)
        .where(InstallationEstimateRevision.id.in_(ids)))).all()
    by_id = {revision.id: (revision, estimate) for revision, estimate in revisions}
    presentations = {}
    projected_cache = {}
    for link in links:
        pair = by_id.get(link.installation_estimate_revision_id)
        if pair is None:
            continue
        revision, estimate = pair
        if estimate.order_id != link.order_id or estimate.proposal_id != link.proposal_id:
            continue
        if revision.snapshot.get("commercial_projection_version") != 2:
            if link.installation_projection_mode != "collapsed" or not revision.snapshot.get("result"):
                continue
            result = InstallationPreviewResponse.model_validate(revision.snapshot["result"])
            projected, _ = InstallationEstimateConfirmationService._projection(revision, "collapsed")
            if len(projected) != 1 or link.installation_line_index != 0 or link.quantity != 1 or \
               link.title != projected[0][0] or Decimal(str(link.price)) != projected[0][1]:
                continue
            grouped = grouped_installation_lines(result, include_policy_notes=False)
            presentations[link.id] = {"installation_display_lines": [item.model_dump() for item in grouped]}
            continue
        cache_key = (revision.id, link.installation_projection_mode)
        if cache_key not in projected_cache:
            projected_cache[cache_key] = InstallationEstimateConfirmationService.commercial_lines(revision, link.installation_projection_mode)
        lines = projected_cache[cache_key]
        index = link.installation_line_index
        if index is not None and 0 <= index < len(lines) and lines[index].description:
            presentations[link.id] = {"description": lines[index].description}
    return presentations


async def frozen_installation_descriptions(session, links) -> dict[int, str]:
    return {link_id: value["description"] for link_id, value in
            (await frozen_installation_presentations(session, links)).items() if value.get("description")}
