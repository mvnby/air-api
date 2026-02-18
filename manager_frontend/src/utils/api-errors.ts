type ApiErrorLike = {
  body?: { detail?: unknown };
  status?: number;
  message?: string;
  statusText?: string;
};

type ValidationItem = {
  loc?: unknown[];
  msg?: string;
};

type StructuredDetail = {
  message?: string;
  error_code?: string;
  field_errors?: Record<string, string>;
};

const ERROR_CODE_MESSAGES: Record<string, string> = {
  validation_error: 'Проверьте заполнение полей формы',
  bad_request: 'Проверьте введенные данные',
  internal_error: 'Внутренняя ошибка сервера',
  lead_not_found: 'Лид не найден',
  order_not_found: 'Сделка не найдена',
  customer_not_found: 'Клиент не найден',
  product_not_found: 'Товар не найден',
  document_generation_failed: 'Не удалось сформировать документ',
};

export const getApiErrorCode = (error: unknown): string | null => {
  const maybe = error as ApiErrorLike;
  const detail = maybe?.body?.detail;
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null;
  const payload = detail as StructuredDetail;
  return typeof payload.error_code === 'string' ? payload.error_code : null;
};

export const getApiErrorMessage = (error: unknown): string => {
  const maybe = error as ApiErrorLike;
  const detail = maybe?.body?.detail;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    const first = detail[0] as ValidationItem;
    if (first?.msg) {
      const loc = Array.isArray(first.loc) ? first.loc.join('.') : '';
      return loc ? `${loc}: ${first.msg}` : first.msg;
    }
    return JSON.stringify(detail);
  }

  if (detail && typeof detail === 'object') {
    const payload = detail as StructuredDetail;
    if (payload.message) return payload.message;
    const mappedMessage = payload.error_code ? ERROR_CODE_MESSAGES[payload.error_code] : undefined;
    if (mappedMessage) return mappedMessage;
    return JSON.stringify(detail);
  }
  if (maybe?.message) return maybe.message;
  if (maybe?.status) return `HTTP ${maybe.status}${maybe.statusText ? ` ${maybe.statusText}` : ''}`;
  return 'Неизвестная ошибка';
};

export const parseApiFieldErrors = (
  error: unknown,
  allowedFields: readonly string[],
): { message: string; fieldErrors: Record<string, string> } => {
  const allowed = new Set(allowedFields);
  const maybe = error as ApiErrorLike;
  const detail = maybe?.body?.detail;
  const fieldErrors: Record<string, string> = {};
  let message = getApiErrorMessage(error);

  if (Array.isArray(detail)) {
    for (const item of detail as ValidationItem[]) {
      if (!item?.msg || !Array.isArray(item.loc) || !item.loc.length) continue;
      const field = String(item.loc[item.loc.length - 1] || '');
      if (!field || !allowed.has(field)) continue;
      if (!fieldErrors[field]) fieldErrors[field] = item.msg;
    }
    if (Object.keys(fieldErrors).length) {
      message = 'Проверьте заполнение полей формы';
    }
  }

  if (detail && typeof detail === 'object') {
    const payload = detail as StructuredDetail;
    if (payload.field_errors && typeof payload.field_errors === 'object') {
      for (const [field, msg] of Object.entries(payload.field_errors)) {
        if (!allowed.has(field) || !msg) continue;
        if (!fieldErrors[field]) fieldErrors[field] = msg;
      }
    }
    if (payload.message && Object.keys(fieldErrors).length) {
      message = payload.message;
    } else {
      const mappedMessage = payload.error_code ? ERROR_CODE_MESSAGES[payload.error_code] : undefined;
      if (mappedMessage) {
        message = mappedMessage;
      }
    }
  }

  return { message, fieldErrors };
};
