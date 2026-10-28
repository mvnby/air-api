"""Two-stage installation terms; payment obligations never record a payment."""

from decimal import Decimal, InvalidOperation

from modules.documents.domain.consumer_terms import ConsumerDocumentTerms, STAGED_INSTALLATION_DOCUMENT_TYPES
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
    if document_type not in STAGED_INSTALLATION_DOCUMENT_TYPES:
        raise ValueError("Монтаж в два этапа доступен для поставки с монтажом и монтажа оборудования заказчика")
    if not 1 <= terms.installation_unit_count <= 1000:
        raise ValueError("Укажите количество кондиционеров от 1 до 1000")
    total = Decimal(money(total))
    remaining_default = Decimal(100 if terms.installation_outdoor_unit_in_first_stage else 200) * terms.installation_unit_count
    try:
        remaining = (
            Decimal(terms.installation_remaining_amount)
            if terms.installation_remaining_amount is not None
            else None
        )
        first = (
            Decimal(terms.installation_first_stage_amount)
            if terms.installation_first_stage_amount is not None
            else total - (remaining if remaining is not None else remaining_default)
        )
    except InvalidOperation as exc:
        raise ValueError("Укажите сумму к оплате за первый этап") from exc
    if not first.is_finite() or first <= 0 or first >= total:
        raise ValueError("Сумма первого этапа должна быть больше нуля и меньше общей суммы")
    if first != first.quantize(Decimal("0.01")):
        raise ValueError("Укажите сумму первого этапа с точностью до копеек")
    if remaining is not None and (not remaining.is_finite() or remaining != total - first):
        raise ValueError("Суммы этапов должны совпадать с общей стоимостью выбранного предложения")
    first_works = (
        "Установка наружного блока, штробление и прокладка коммуникаций."
        if terms.installation_outdoor_unit_in_first_stage
        else "Штробление и прокладка коммуникаций."
    )
    second_works = (
        "Установка внутреннего блока, подключение и пусконаладочные работы."
        if terms.installation_outdoor_unit_in_first_stage
        else "Установка наружного и внутреннего блоков, подключение и пусконаладочные работы."
    )
    due = (
        "После завершения ремонта и готовности помещения; дата выезда "
        "согласовывается сторонами. Остаток оплачивается после выполнения и приемки второго этапа."
    )
    overrides = (
        terms.installation_first_stage_works,
        terms.installation_second_stage_works,
        terms.installation_second_stage_due,
    )
    if any(value is not None and not value.strip() for value in overrides):
        raise ValueError("Заполните состав работ и условия завершения этапов")
    values.update({
        "installation.first_stage_amount": money(first),
        "installation.remaining_amount": money(total - first),
        "installation.first_stage_works": (terms.installation_first_stage_works or first_works).strip(),
        "installation.second_stage_works": (terms.installation_second_stage_works or second_works).strip(),
        "installation.second_stage_due": (terms.installation_second_stage_due or due).strip(),
    })
    return values, conditions


def staged_template_is_supported(schema: dict) -> bool:
    return (
        STAGED_INSTALLATION_FIELDS <= set(schema.get("fields", []))
        and STAGED_INSTALLATION_CONDITIONS <= set(schema.get("conditions", []))
    )
