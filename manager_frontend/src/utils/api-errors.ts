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
    const payload = detail as { message?: string };
    if (payload.message) return payload.message;
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
    const payload = detail as { message?: string; field_errors?: Record<string, string> };
    if (payload.field_errors && typeof payload.field_errors === 'object') {
      for (const [field, msg] of Object.entries(payload.field_errors)) {
        if (!allowed.has(field) || !msg) continue;
        if (!fieldErrors[field]) fieldErrors[field] = msg;
      }
    }
    if (payload.message && Object.keys(fieldErrors).length) {
      message = payload.message;
    }
  }

  return { message, fieldErrors };
};
