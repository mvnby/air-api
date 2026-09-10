import type { ProductOption } from './order-editor-types';

const scalarText = (value: unknown): string => {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '';
    return String(value).replace('.', ',');
  }
  if (typeof value !== 'string') return '';
  const cleaned = value.trim();
  if (!cleaned) return '';
  if (/^-?\d+(?:[.,]\d+)?$/.test(cleaned)) return cleaned.replace('.', ',');
  return cleaned;
};

const withUnit = (value: unknown, unit: string): string => {
  const text = scalarText(value);
  if (!text) return '';
  return /[a-zа-яё°%²³]/i.test(text) ? text : `${text} ${unit}`;
};

const explicitBoolean = (value: unknown): boolean | null => {
  if (typeof value === 'boolean') return value;
  const normalized = String(value ?? '').trim().toLocaleLowerCase('ru');
  if (['true', 'yes', 'да', '1', 'инвертор', 'inverter'].includes(normalized)) return true;
  if (['false', 'no', 'нет', '0', 'on/off', 'on-off'].includes(normalized)) return false;
  return null;
};

export const buildKnownProductClientDescription = (product: ProductOption): string => {
  const specs = product.specs || {};
  const parts: string[] = [];
  const compressorType = scalarText(specs.compressor_type_norm).toLowerCase();
  const legacyInverter = explicitBoolean(specs.inverter);
  if (
    product.is_inverter === true
    || ['inverter', 'full_dc'].includes(compressorType)
    || (!compressorType && legacyInverter === true)
  ) {
    parts.push('Инвертор');
  } else if (compressorType === 'on_off') {
    parts.push('On/Off');
  }

  const indoorType = scalarText(specs.indoor_type || specs.indoor_unit_type);
  if (indoorType) {
    parts.push(`тип внутреннего блока: ${indoorType}`);
  } else if (product.product_kind === 'indoor_unit') {
    parts.push('внутренний блок');
  } else if (product.product_kind === 'outdoor_unit') {
    parts.push('наружный блок');
  }

  const area = withUnit(specs.area_m2, 'м²');
  if (area) parts.push(`площадь: ${area}`);

  const cooling = withUnit(
    specs.capacity_cooling_kw ?? product.power_cooling,
    'кВт',
  );
  if (cooling) parts.push(`охлаждение: ${cooling}`);

  const heating = withUnit(specs.capacity_heating_kw, 'кВт');
  if (heating) parts.push(`обогрев: ${heating}`);

  const noise = withUnit(specs.noise_indoor, 'дБ');
  if (noise) parts.push(`шум внутреннего блока: ${noise}`);

  const temperature = withUnit(specs.temp_range_heat, '°C');
  if (temperature) parts.push(`обогрев при наружной температуре: ${temperature}`);

  const color = scalarText(specs.color);
  if (color) parts.push(`цвет: ${color}`);

  return parts.join('; ');
};
