export type EditableSpec = { key: string; value: string };

const WIFI_KEYS = new Set(['wifi_state', 'wifi_ready', 'wifi_builtin']);
const ENERGY_CLASS_KEYS = new Set(['energy_class_cooling', 'energy_class_heating']);

const normalizeBoolean = (value: unknown): boolean | null => {
  const token = String(value ?? '').trim().toLowerCase();
  if (['1', 'true', 'yes', 'да', 'есть', 'встроен', 'встроенный'].includes(token)) return true;
  if (['0', 'false', 'no', 'нет', 'отсутствует'].includes(token)) return false;
  return null;
};

export const canonicalEnergyClass = (value: string): string => (
  value.trim().replace(/[Аа]/g, 'A').replace(/\s+/g, '')
);

export const collapseWifiSpecs = (entries: EditableSpec[]): EditableSpec[] => {
  const values = new Map(entries.map((entry) => [entry.key, entry.value]));
  const explicitState = String(values.get('wifi_state') || '').trim().toLowerCase();
  const builtin = normalizeBoolean(values.get('wifi_builtin'));
  const ready = normalizeBoolean(values.get('wifi_ready'));
  const state = ['builtin', 'ready', 'none'].includes(explicitState)
    ? explicitState
    : builtin === true
      ? 'builtin'
      : ready === true
        ? 'ready'
        : builtin === false || ready === false
          ? 'none'
          : '';

  const normalized = entries
    .filter((entry) => !WIFI_KEYS.has(entry.key))
    .map((entry) => (
      ENERGY_CLASS_KEYS.has(entry.key)
        ? { ...entry, value: canonicalEnergyClass(entry.value) }
        : entry
    ));
  if (state) normalized.push({ key: 'wifi_state', value: state });
  return normalized;
};

export const isTechnicalSpecKey = (key: string): boolean => key === 'brand';

export const getLegacySpecSuggestion = (
  key: string,
  value: string,
): { value: string; message: string } | null => {
  if (!['pipe_liquid', 'pipe_gas'].includes(key)) return null;
  const token = value.trim().replace(',', '.');
  const suggestion = token === '3' ? '3/8"' : token === '5' ? '5/8"' : '';
  if (!suggestion) return null;
  return {
    value: suggestion,
    message: `Значение «${value}» не соответствует формату диаметра. Проверьте преобразование в ${suggestion}.`,
  };
};
