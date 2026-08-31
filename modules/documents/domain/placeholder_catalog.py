from __future__ import annotations

from dataclasses import dataclass

from .consumer_terms import B2C_NATIVE_DOCUMENT_TYPES


@dataclass(frozen=True, slots=True)
class PlaceholderDescriptor:
    name: str
    label: str
    group: str


@dataclass(frozen=True, slots=True)
class ConditionDescriptor:
    name: str
    label: str
    group: str


SCALAR_PLACEHOLDERS: tuple[PlaceholderDescriptor, ...] = (
    PlaceholderDescriptor(
        "document.internal_reference", "Внутренний номер CRM", "Документ"
    ),
    PlaceholderDescriptor("document.official_series", "Официальная серия", "Документ"),
    PlaceholderDescriptor(
        "document.official_number", "Официальный номер без серии", "Документ"
    ),
    PlaceholderDescriptor(
        "document.official_full_number", "Серия и официальный номер", "Документ"
    ),
    PlaceholderDescriptor("document.issued_on", "Дата документа", "Документ"),
    PlaceholderDescriptor("document.issue_city", "Город документа", "Документ"),
    PlaceholderDescriptor("document.type", "Тип документа", "Документ"),
    PlaceholderDescriptor("document.business_role", "Роль счета", "Документ"),
    PlaceholderDescriptor(
        "document.act_sequence_number", "Порядковый номер акта", "Документ"
    ),
    PlaceholderDescriptor("transport.car_model", "Марка автомобиля", "Транспорт"),
    PlaceholderDescriptor(
        "transport.car_number", "Регистрационный номер автомобиля", "Транспорт"
    ),
    PlaceholderDescriptor("transport.driver_name", "ФИО водителя", "Транспорт"),
    PlaceholderDescriptor("transport.carrier", "Перевозчик", "Транспорт"),
    PlaceholderDescriptor("basis.type", "Тип документа-основания", "Основание"),
    PlaceholderDescriptor("basis.number", "Номер документа-основания", "Основание"),
    PlaceholderDescriptor("basis.date", "Дата документа-основания", "Основание"),
    PlaceholderDescriptor(
        "seller.display_name", "Краткое наименование продавца", "Продавец"
    ),
    PlaceholderDescriptor(
        "seller.legal_name", "Полное наименование продавца", "Продавец"
    ),
    PlaceholderDescriptor("seller.unp", "УНП продавца", "Продавец"),
    PlaceholderDescriptor("seller.city", "Город продавца", "Продавец"),
    PlaceholderDescriptor("seller.entity_type", "Тип продавца (код)", "Продавец"),
    PlaceholderDescriptor("seller.entity_type_label", "Тип продавца", "Продавец"),
    PlaceholderDescriptor("seller.is_vat_payer", "Признак плательщика НДС", "Продавец"),
    PlaceholderDescriptor(
        "seller.signing_mode", "Способ подписания продавцом (код)", "Продавец"
    ),
    PlaceholderDescriptor(
        "seller.legal_address", "Юридический адрес продавца", "Продавец"
    ),
    PlaceholderDescriptor(
        "seller.postal_address", "Почтовый адрес продавца", "Продавец"
    ),
    PlaceholderDescriptor("seller.bank_name", "Банк продавца", "Продавец"),
    PlaceholderDescriptor("seller.iban", "IBAN продавца", "Продавец"),
    PlaceholderDescriptor("seller.bic", "BIC продавца", "Продавец"),
    PlaceholderDescriptor(
        "seller.director_title", "Должность подписанта продавца", "Продавец"
    ),
    PlaceholderDescriptor(
        "seller.director_name", "ФИО подписанта продавца", "Продавец"
    ),
    PlaceholderDescriptor(
        "seller.acts_on_basis", "Основание полномочий продавца", "Продавец"
    ),
    PlaceholderDescriptor(
        "seller.signer_position", "Должность подписанта продавца", "Продавец"
    ),
    PlaceholderDescriptor("seller.signer_name", "ФИО подписанта продавца", "Продавец"),
    PlaceholderDescriptor(
        "seller.acting_basis", "Основание полномочий продавца", "Продавец"
    ),
    PlaceholderDescriptor("seller.phone", "Телефон продавца", "Продавец"),
    PlaceholderDescriptor("seller.email", "Email продавца", "Продавец"),
    PlaceholderDescriptor(
        "customer.display_name", "Краткое наименование клиента", "Клиент"
    ),
    PlaceholderDescriptor(
        "customer.full_name", "Полное наименование клиента", "Клиент"
    ),
    PlaceholderDescriptor("customer.phone", "Телефон клиента", "Клиент"),
    PlaceholderDescriptor("customer.email", "Email клиента", "Клиент"),
    PlaceholderDescriptor("customer.unp", "УНП клиента", "Клиент"),
    PlaceholderDescriptor("customer.city", "Город клиента", "Клиент"),
    PlaceholderDescriptor("customer.entity_type", "Тип клиента (код)", "Клиент"),
    PlaceholderDescriptor("customer.entity_type_label", "Тип клиента", "Клиент"),
    PlaceholderDescriptor(
        "customer.signing_mode", "Способ подписания клиентом (код)", "Клиент"
    ),
    PlaceholderDescriptor(
        "customer.legal_address", "Юридический адрес клиента", "Клиент"
    ),
    PlaceholderDescriptor("customer.bank_name", "Банк клиента", "Клиент"),
    PlaceholderDescriptor("customer.iban", "IBAN клиента", "Клиент"),
    PlaceholderDescriptor("customer.bic", "BIC клиента", "Клиент"),
    PlaceholderDescriptor(
        "customer.signer_position", "Должность подписанта клиента", "Клиент"
    ),
    PlaceholderDescriptor("customer.signer_name", "ФИО подписанта клиента", "Клиент"),
    PlaceholderDescriptor(
        "customer.acting_basis", "Основание полномочий клиента", "Клиент"
    ),
    PlaceholderDescriptor("order.id", "ID заказа", "Заказ"),
    PlaceholderDescriptor("order.title", "Название заказа", "Заказ"),
    PlaceholderDescriptor("order.object_title", "Название объекта", "Заказ"),
    PlaceholderDescriptor("order.object_address", "Адрес объекта", "Заказ"),
    PlaceholderDescriptor("proposal.name", "Название предложения", "Предложение"),
    PlaceholderDescriptor("contract.scenario", "Сценарий договора (код)", "Договор"),
    PlaceholderDescriptor("contract.scenario_label", "Сценарий договора", "Договор"),
    PlaceholderDescriptor("contract.subject", "Предмет договора", "Договор"),
    PlaceholderDescriptor("contract.valid_until", "Срок действия договора", "Договор"),
    PlaceholderDescriptor("contract.delivery_deadline", "Срок поставки", "Договор"),
    PlaceholderDescriptor(
        "contract.performance_deadline", "Срок выполнения работ", "Договор"
    ),
    PlaceholderDescriptor(
        "contract.additional_conditions", "Дополнительные условия", "Договор"
    ),
    PlaceholderDescriptor("payment.summary", "Краткое условие оплаты", "Оплата"),
    PlaceholderDescriptor("payment.total", "Сумма по графику", "Оплата"),
    PlaceholderDescriptor("payment.prepayment_amount", "Сумма предоплаты", "Оплата"),
    PlaceholderDescriptor("payment.balance_amount", "Остаток оплаты", "Оплата"),
    PlaceholderDescriptor("payment.currency", "Валюта оплаты", "Оплата"),
    PlaceholderDescriptor("offer.url", "Ссылка на публичную оферту", "Оферта"),
    PlaceholderDescriptor("offer.version", "Версия оферты", "Оферта"),
    PlaceholderDescriptor("offer.published_on", "Дата публикации оферты", "Оферта"),
    PlaceholderDescriptor("equipment.brand", "Бренд оборудования", "Оборудование"),
    PlaceholderDescriptor("equipment.model", "Модель оборудования", "Оборудование"),
    PlaceholderDescriptor(
        "equipment.serial", "Серийный номер оборудования", "Оборудование"
    ),
    PlaceholderDescriptor(
        "equipment.display_name", "Наименование оборудования", "Оборудование"
    ),
    PlaceholderDescriptor(
        "warranty.goods.months", "Гарантия на оборудование, мес.", "Гарантия"
    ),
    PlaceholderDescriptor(
        "warranty.goods.terms", "Условия гарантии на оборудование", "Гарантия"
    ),
    PlaceholderDescriptor(
        "warranty.work.months", "Гарантия на работы, мес.", "Гарантия"
    ),
    PlaceholderDescriptor(
        "warranty.work.terms", "Условия гарантии на работы", "Гарантия"
    ),
    PlaceholderDescriptor("route.length_meters", "Длина трассы, м", "Трасса"),
    PlaceholderDescriptor(
        "route.liquid_pipe_diameter_mm", "Диаметр жидкостной трубы, мм", "Трасса"
    ),
    PlaceholderDescriptor(
        "route.gas_pipe_diameter_mm", "Диаметр газовой трубы, мм", "Трасса"
    ),
    PlaceholderDescriptor("route.drainage", "Дренаж", "Трасса"),
    PlaceholderDescriptor("route.power_supply", "Электропитание", "Трасса"),
    PlaceholderDescriptor("route.notes", "Примечания по трассе", "Трасса"),
    PlaceholderDescriptor(
        "route.photo_fixation_status", "Статус фотофиксации", "Трасса"
    ),
    PlaceholderDescriptor("route.pressure_test_status", "Статус опрессовки", "Трасса"),
    PlaceholderDescriptor(
        "route.ends_capped_status", "Статус заглушки трассы", "Трасса"
    ),
    PlaceholderDescriptor("act.result_text", "Результат работ", "Акт"),
    PlaceholderDescriptor("act.claims_text", "Замечания заказчика", "Акт"),
    PlaceholderDescriptor("act.acceptance_deadline", "Срок приемки", "Акт"),
    PlaceholderDescriptor("totals.amount", "Сумма", "Итоги"),
    PlaceholderDescriptor("totals.amount_in_words", "Сумма прописью", "Итоги"),
    PlaceholderDescriptor("totals.currency", "Валюта", "Итоги"),
    PlaceholderDescriptor("totals.vat_label", "С НДС или без НДС", "Итоги"),
    PlaceholderDescriptor("totals.quantity", "Общее количество", "Итоги"),
    PlaceholderDescriptor(
        "totals.quantity_in_words", "Общее количество прописью", "Итоги"
    ),
    PlaceholderDescriptor("totals.weight", "Общая масса", "Итоги"),
    PlaceholderDescriptor("totals.weight_in_words", "Общая масса прописью", "Итоги"),
)


CONDITIONAL_FLAGS: tuple[ConditionDescriptor, ...] = tuple(
    ConditionDescriptor(name, label, group)
    for group, prefix, party_label in (
        ("Условия · продавец", "seller", "продавец"),
        ("Условия · клиент", "customer", "клиент"),
    )
    for name, label in (
        (f"{prefix}.is_organization", f"{party_label.capitalize()} — организация"),
        (
            f"{prefix}.is_individual_entrepreneur",
            f"{party_label.capitalize()} — ИП",
        ),
        (f"{prefix}.is_individual", f"{party_label.capitalize()} — физлицо"),
        (f"{prefix}.signs_self", f"{party_label.capitalize()} подписывает лично"),
        (
            f"{prefix}.signs_as_statutory_body",
            f"{party_label.capitalize()} подписывает через руководителя",
        ),
        (
            f"{prefix}.signs_by_power_of_attorney",
            f"{party_label.capitalize()} подписывает по доверенности",
        ),
        (
            f"{prefix}.organization_statutory_body",
            f"Организация-{party_label} подписывает через руководителя",
        ),
        (
            f"{prefix}.organization_power_of_attorney",
            f"Организация-{party_label} подписывает по доверенности",
        ),
        (
            f"{prefix}.individual_entrepreneur_self",
            f"ИП-{party_label} подписывает лично",
        ),
        (
            f"{prefix}.individual_entrepreneur_power_of_attorney",
            f"ИП-{party_label} подписывает по доверенности",
        ),
        (
            f"{prefix}.individual_self",
            f"Физлицо-{party_label} подписывает лично",
        ),
        (
            f"{prefix}.individual_power_of_attorney",
            f"Физлицо-{party_label} подписывает по доверенности",
        ),
    )
)

CONDITIONAL_FLAGS += (
    ConditionDescriptor(
        "document.invoice_is_payment_request",
        "Счёт только для оплаты",
        "Документ",
    ),
    ConditionDescriptor(
        "document.invoice_is_offer",
        "Счёт является офертой",
        "Документ",
    ),
    ConditionDescriptor("seller.is_vat_payer", "Продавец платит НДС", "Продавец"),
    ConditionDescriptor(
        "seller.is_not_vat_payer", "Продавец не платит НДС", "Продавец"
    ),
    ConditionDescriptor("order.has_object_address", "Указан адрес объекта", "Заказ"),
    *(
        ConditionDescriptor(f"contract.is_{scenario}", f"Договор: {label}", "Договор")
        for scenario, label in (
            ("services", "услуги"),
            ("repair", "диагностика и ремонт"),
            ("maintenance", "техническое обслуживание"),
            ("supply_installation", "поставка с монтажом"),
            ("installation", "монтаж"),
            ("framework", "рамочный"),
            ("supply", "поставка оборудования"),
        )
    ),
    ConditionDescriptor("contract.framework", "Рамочный договор", "Договор"),
    ConditionDescriptor("contract.has_subject", "Указан предмет договора", "Договор"),
    ConditionDescriptor(
        "contract.has_additional_conditions", "Есть дополнительные условия", "Договор"
    ),
    ConditionDescriptor(
        "contract.has_delivery_deadline", "Указан срок поставки", "Договор"
    ),
    ConditionDescriptor(
        "contract.has_no_delivery_deadline", "Срок поставки не указан", "Договор"
    ),
    ConditionDescriptor(
        "contract.has_performance_deadline", "Указан срок выполнения работ", "Договор"
    ),
    ConditionDescriptor(
        "contract.has_no_performance_deadline",
        "Срок выполнения работ не указан",
        "Договор",
    ),
    ConditionDescriptor(
        "contract.has_any_deadline", "Указан хотя бы один срок", "Договор"
    ),
    ConditionDescriptor(
        "contract.has_no_deadlines", "Сроки поставки и работ не указаны", "Договор"
    ),
    ConditionDescriptor("payment.has_schedule", "Есть график оплаты", "Оплата"),
    ConditionDescriptor("payment.is_full_prepayment", "100% предоплата", "Оплата"),
    ConditionDescriptor(
        "payment.is_equipment_prepayment_balance",
        "Предоплата за оборудование и остаток после работ",
        "Оплата",
    ),
    ConditionDescriptor(
        "payment.is_postpayment", "Оплата после работ или приемки", "Оплата"
    ),
    ConditionDescriptor(
        "payment.is_custom_schedule", "Индивидуальный график оплаты", "Оплата"
    ),
    ConditionDescriptor(
        "warranty.goods.present", "Указана гарантия на оборудование", "Гарантия"
    ),
    ConditionDescriptor(
        "warranty.work.present", "Указана гарантия на работы", "Гарантия"
    ),
    ConditionDescriptor(
        "warranty.any_present", "Указана хотя бы одна гарантия", "Гарантия"
    ),
    ConditionDescriptor(
        "route.photo_fixation_performed", "Выполнена фотофиксация", "Трасса"
    ),
    ConditionDescriptor(
        "route.pressure_test_performed", "Выполнена опрессовка", "Трасса"
    ),
    ConditionDescriptor("route.ends_capped", "Концы трассы заглушены", "Трасса"),
    ConditionDescriptor("act.claims_present", "Есть замечания", "Акт"),
    ConditionDescriptor("act.no_claims", "Замечаний нет", "Акт"),
    ConditionDescriptor("act.has_result", "Указан результат работ", "Акт"),
    ConditionDescriptor("act.has_acceptance_deadline", "Указан срок приемки", "Акт"),
)

LINE_ROW_PLACEHOLDERS: tuple[PlaceholderDescriptor, ...] = (
    PlaceholderDescriptor("line.number", "Номер строки", "Строки"),
    PlaceholderDescriptor("line.title", "Наименование", "Строки"),
    PlaceholderDescriptor("line.kind", "Товар или услуга", "Строки"),
    PlaceholderDescriptor("line.country", "Страна происхождения", "Строки"),
    PlaceholderDescriptor("line.unit", "Единица измерения", "Строки"),
    PlaceholderDescriptor("line.quantity", "Количество", "Строки"),
    PlaceholderDescriptor("line.unit_price", "Цена за единицу", "Строки"),
    PlaceholderDescriptor("line.amount", "Сумма строки", "Строки"),
    PlaceholderDescriptor("line.vat_label", "Налоговый режим строки", "Строки"),
    PlaceholderDescriptor("line.seats", "Количество грузовых мест", "Строки"),
    PlaceholderDescriptor("line.mass", "Масса", "Строки"),
    PlaceholderDescriptor("line.note", "Примечание", "Строки"),
)

PAYMENT_SCHEDULE_ROW_PLACEHOLDERS: tuple[PlaceholderDescriptor, ...] = (
    PlaceholderDescriptor("payment.number", "Номер платежа", "График оплаты"),
    PlaceholderDescriptor("payment.share_percent", "Доля, %", "График оплаты"),
    PlaceholderDescriptor("payment.amount", "Сумма", "График оплаты"),
    PlaceholderDescriptor("payment.due_event", "Срок оплаты", "График оплаты"),
    PlaceholderDescriptor("payment.due_days", "Количество дней", "График оплаты"),
    PlaceholderDescriptor("payment.due_day_kind", "Вид дней", "График оплаты"),
    PlaceholderDescriptor("payment.note", "Примечание", "График оплаты"),
)

SUPPORTED_NATIVE_DOCUMENT_TYPES = (
    frozenset({"offer", "invoice", "contract", "act", "tn2", "ttn1"})
    | B2C_NATIVE_DOCUMENT_TYPES
)
