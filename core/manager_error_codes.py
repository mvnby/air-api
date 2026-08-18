VALIDATION_ERROR = "validation_error"
INTERNAL_ERROR = "internal_error"
BAD_REQUEST = "bad_request"
FORBIDDEN = "forbidden"
LEAD_NOT_FOUND = "lead_not_found"
ORDER_NOT_FOUND = "order_not_found"
CUSTOMER_NOT_FOUND = "customer_not_found"
EQUIPMENT_NOT_FOUND = "equipment_not_found"
PRODUCT_NOT_FOUND = "product_not_found"
DOCUMENT_GENERATION_FAILED = "document_generation_failed"
DOCUMENT_NOT_FOUND = "document_not_found"
DOCUMENT_HAS_DEPENDENTS = "document_has_dependents"
ORDER_DOCUMENTS_LOCKED = "order_documents_locked"


# Shared message map for manager API responses and frontend fallback mapping.
DEFAULT_MANAGER_ERROR_MESSAGES = {
    VALIDATION_ERROR: "Проверьте заполнение полей формы",
    INTERNAL_ERROR: "Внутренняя ошибка сервера",
    BAD_REQUEST: "Проверьте введенные данные",
    FORBIDDEN: "Недостаточно прав для выполнения операции",
    LEAD_NOT_FOUND: "Лид не найден",
    ORDER_NOT_FOUND: "Сделка не найдена",
    CUSTOMER_NOT_FOUND: "Клиент не найден",
    EQUIPMENT_NOT_FOUND: "Оборудование не найдено",
    PRODUCT_NOT_FOUND: "Товар не найден",
    DOCUMENT_GENERATION_FAILED: "Не удалось сформировать документ",
    DOCUMENT_NOT_FOUND: "Документ не найден",
    DOCUMENT_HAS_DEPENDENTS: "Нельзя удалить документ-основание: сначала удалите связанные акты или накладные",
    ORDER_DOCUMENTS_LOCKED: "Заказ завершён: документы доступны только для просмотра и повторной отправки",

}


def resolve_manager_error_message(error_code: str, message: str | None = None) -> str:
    if message:
        return message
    return DEFAULT_MANAGER_ERROR_MESSAGES.get(error_code, "Ошибка запроса")
