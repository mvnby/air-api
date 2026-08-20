export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_UTF8_BYTES = 72;
const PASSWORD_GENERATOR_LENGTH = 24;
const PASSWORD_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

export const passwordUtf8Bytes = (value: string): number => new TextEncoder().encode(value).length;

export const passwordPolicyMessage = (value: string): string | null => {
  if (Array.from(value).length < PASSWORD_MIN_LENGTH) {
    return `Новый пароль должен содержать минимум ${PASSWORD_MIN_LENGTH} символов`;
  }
  if (passwordUtf8Bytes(value) > PASSWORD_MAX_UTF8_BYTES) {
    return `Новый пароль не должен превышать ${PASSWORD_MAX_UTF8_BYTES} байта в UTF-8`;
  }
  return null;
};

export const generateManagerPassword = (): string => {
  const values = new Uint8Array(PASSWORD_GENERATOR_LENGTH);
  window.crypto.getRandomValues(values);
  return Array.from(values, (value) => PASSWORD_ALPHABET[value & 63]).join('');
};
