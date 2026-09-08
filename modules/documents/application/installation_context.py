"""Two-stage installation terms; payment obligations never record a payment."""

from decimal import Decimal, InvalidOperation

from modules.documents.domain.consumer_terms import ConsumerDocumentTerms
from .value_formatters import money


STAGED_INSTALLATION_FIELDS = frozenset({
    "installation.first_stage_amount", "installation.remaining_amount",
    "installation.first_stage_works", "installation.second_stage_works",
    "installation.second_stage_due",
})
STAGED_INSTALLATION_CONDITIONS = frozenset({
    "installation.two_stages", "installation.single_stage",
})


def build_installation_context(
    *, document_type: str, terms: ConsumerDocumentTerms, total: Decimal,
) -> tuple[dict[str, str], dict[str, bool]]:
    enabled = terms.installation_two_stages
    values = dict.fromkeys(STAGED_INSTALLATION_FIELDS, "")
    conditions = {
        "installation.two_stages": enabled,
        "installation.single_stage": not enabled,
    }
    if not enabled:
        return values, conditions
    if document_type != "b2c_supply_installation_act":
        raise ValueError("Монтаж в два этапа доступен для продажи с монтажом")
    try:
        first = Decimal(str(terms.installation_first_stage_amount or ""))
    except InvalidOperation as exc:
        raise ValueError("Укажите сумму к оплате за первый этап") from exc
    total = Decimal(money(total))
    if not first.is_finite() or first <= 0 or first >= total:
        raise ValueError("Сумма первого этапа должна быть больше нуля и меньше общей суммы")
    if first != first.quantize(Decimal("0.01")):
        raise ValueError("Укажите сумму первого этапа с точностью до копеек")
    values.update({
        "installation.first_stage_amount": money(first),
        "installation.remaining_amount": money(total - first),
        "installation.first_stage_works": (
            "Установка наружного блока, штробление и прокладка коммуникаций."
        ),
        "installation.second_stage_works": (
            "Установка внутреннего блока, подключение и пусконаладочные работы."
        ),
        "installation.second_stage_due": (
            "После завершения ремонта и готовности помещения; дата выезда "
            "согласовывается сторонами. Остаток оплачивается после выполнения второго этапа."
        ),
    })
    return values, conditions


def staged_template_is_supported(schema: dict) -> bool:
    return (
        STAGED_INSTALLATION_FIELDS <= set(schema.get("fields", []))
        and STAGED_INSTALLATION_CONDITIONS <= set(schema.get("conditions", []))
    )
