from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaceholderDescriptor:
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
    PlaceholderDescriptor("seller.entity_type", "Тип продавца (код)", "Продавец"),
    PlaceholderDescriptor(
        "seller.entity_type_label", "Тип продавца", "Продавец"
    ),
    PlaceholderDescriptor("seller.is_vat_payer", "Признак плательщика НДС", "Продавец"),
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

SUPPORTED_NATIVE_DOCUMENT_TYPES = frozenset(
    {"offer", "invoice", "contract", "act", "tn2", "ttn1"}
)
