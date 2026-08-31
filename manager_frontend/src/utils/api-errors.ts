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

const FIELD_LABELS: Record<string, string> = {
  service_kind: 'Направление',
  selector_label: 'Короткое название',
  estimate_template: 'Шаблон формулировки',
  category: 'Категория',
  power_range: 'Диапазон мощности',
  base_price: 'Базовая цена',
  included_route_meters: 'Включено трассы',
};

const ERROR_CODE_MESSAGES: Record<string, string> = {
  validation_error: 'Проверьте заполнение полей формы',
  bad_request: 'Проверьте введенные данные',
  internal_error: 'Внутренняя ошибка сервера',
  lead_not_found: 'Лид не найден',
  order_not_found: 'Сделка не найдена',
  customer_not_found: 'Клиент не найден',
  customer_already_exists: 'Клиент с такими данными уже существует',
  product_not_found: 'Товар не найден',
  document_generation_failed: 'Не удалось сформировать документ',
};

const formatFieldErrorMessage = (field: string, message: string): string => {
  const label = FIELD_LABELS[field] ?? field;
  if (field === 'service_kind' && /Input should be/.test(message)) {
    return `${label}: запущенный API ещё не поддерживает выбранное направление. Перезапустите backend и повторите действие.`;
  }
  return `${label}: ${message}`;
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
    if (payload.error_code === 'customer_already_exists' && payload.message) {
      return payload.message;
    }
    if (payload.field_errors && typeof payload.field_errors === 'object') {
      const firstFieldError = Object.entries(payload.field_errors).find(([, msg]) => Boolean(msg));
      if (firstFieldError) {
        return formatFieldErrorMessage(firstFieldError[0], firstFieldError[1]);
      }
    }
    if (payload.message) return payload.message;
    const mappedMessage = payload.error_code ? ERROR_CODE_MESSAGES[payload.error_code] : undefined;
    if (mappedMessage) return mappedMessage;
    return JSON.stringify(detail);
  }
  if (maybe?.message) return maybe.message;
  if (maybe?.status) return `HTTP ${maybe.status}${maybe.statusText ? ` ${maybe.statusText}` : ''}`;
  return 'Неизвестная ошибка';
};

export const getApiFieldError = (error: unknown, field: string): string | null => {
  const maybe = error as ApiErrorLike;
  const detail = maybe?.body?.detail;
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null;
  const value = (detail as StructuredDetail).field_errors?.[field];
  return typeof value === 'string' && value ? value : null;
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
      let field = String(item.loc[item.loc.length - 1] || '');
      if (!allowed.has(field)) {
        const nestedField = item.loc.find((part) => typeof part === 'string' && allowed.has(String(part)));
        if (nestedField) field = String(nestedField);
      }
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
    if (payload.message) {
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
