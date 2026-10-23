// Canonical keys and legacy source aliases from services/spec_registry.py.
// Keep these presentation rules in parity with services/product_power_supply.py.
const aliases: Record<string, string[]> = {
  power_supply: ['Электропитание', 'Электропитание, Ф/В/Гц', 'Электропитание, В/Гц/Ф', 'Электропитание (Ø / В / Гц)', 'Электропитание В/Гц/Ф'],
  power_supply_voltage: ['Параметры питающей сети', 'Напряжение, В'],
  power_supply_indoor: ['Внутренний блок: Электропитание, Ф/В/Гц', 'Электропитание внутреннего блока (В / Ø / Гц)', 'Электропитание внутреннего блока В/Гц/Ф', 'Электропитание внутреннего блока, В/Гц/Ф'],
  power_supply_outdoor: ['Наружный блок: Электропитание, Ф/В/Гц', 'Электропитание внешнего блока (В / Ø / Гц)', 'Электропитание наружного блока В/Гц/Ф', 'Электропитание наружного блока, В/Гц/Ф'],
  power_supply_location: ['Подача питания', 'Подключение питания', 'Подключение электропитания', 'Сторона подключения'],
};

type Supply = { text: string; lower: number; upper: number; phase: string | null; uncertain: boolean; conflictingAliases?: boolean };
const voltagePattern = /(?<![\d.,])([1-6]\d{2})(?:\s*-\s*([1-6]\d{2}))?(?![\d.,])/g;

const supply = (value: unknown): Supply | null => {
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  const raw = String(value).replace(/\s+/g, ' ').trim().replace(/[–—]/g, '-')
    .replace(/(?<=\d)\s*[~～]\s*(?=\d)/g, '-');
  if (/\?|не\s*(?:извест|указ|определ|подтвержд)|уточн|предполож|возмож|по запросу|unknown|\bn\/?a\b/i.test(raw)) return null;
  const matches = [...raw.matchAll(voltagePattern)];
  if (!matches.length) return null;
  let text: string;
  let phase: RegExpMatchArray | null = null;
  if (/внутр|наруж|внешн/i.test(raw)) {
    text = raw.replace(voltagePattern, (match: string, _a: string, _b: string, offset: number) => (
      match + (/^\s*[вv]/i.test(raw.slice(offset + match.length)) ? '' : ' В')
    ));
  } else {
    const voltages = matches.map(match => match[1] + (match[2] ? `-${match[2]}` : ''));
    text = `${[...new Set(voltages)].join('/')} В`;
    phase = raw.match(/(?<!\d)([13])\s*(?:ф|ph|n?\s*[~∼])/i)
      || raw.match(/^\s*([13])\s*\//) || raw.match(/\/\s*([13])\s*$/);
    if (phase) text += `, ${phase[1]} ф.`;
    if (/нейтрал|[13]\s*n\s*[~∼]/i.test(raw)) text += ', нейтраль';
  }
  const bounds = matches.flatMap(match => [Number(match[1]), Number(match[2] || match[1])]);
  return { text, lower: Math.min(...bounds), upper: Math.max(...bounds), phase: phase?.[1] || null,
    uncertain: matches.length > 1 && !/внутр|наруж|внешн/i.test(raw) };
};

const overlaps = (first: Supply, second: Supply) => !first.uncertain && !second.uncertain
  && first.lower <= second.upper && second.lower <= first.upper
  && !(first.phase && second.phase && first.phase !== second.phase);

const display = (value: Supply) => value.text + (value.uncertain ? ' (требует уточнения)' : '');

const resolveBlockAggregate = (value: Supply | null, blocks: [string, Supply][]): Supply | null => {
  if (!value || blocks.length !== 2 || blocks.some(([, block]) => block.uncertain)) return value;
  const ranges = [...value.text.matchAll(voltagePattern)].map(match => `${match[1]}-${match[2] || match[1]}`);
  if (ranges.length < 2) return value;
  let resolved = false;
  if (!value.conflictingAliases) {
    if (/внутр|наруж|внешн/i.test(value.text)) {
      const segments = value.text.split(';');
      const matched = new Set<string>();
      for (const segment of segments) {
        const colon = segment.indexOf(':');
        const label = segment.slice(0, colon);
        const role = /внутр/i.test(label) ? 'внутреннего блока' : /наруж|внешн/i.test(label) ? 'наружного блока' : '';
        const stated = colon >= 0 ? supply(segment.slice(colon + 1)) : null;
        const block = blocks.find(([name]) => name === role)?.[1];
        if (stated && block && !stated.uncertain && overlaps(stated, block)
          && stated.lower === block.lower && stated.upper === block.upper
          && (!stated.phase || stated.phase === block.phase)
          && (!stated.text.includes('нейтраль') || block.text.includes('нейтраль'))) matched.add(role);
      }
      resolved = segments.length === 2 && matched.size === 2;
    } else {
      const blockRanges = new Set(blocks.map(([, block]) => `${block.lower}-${block.upper}`));
      resolved = !value.phase && ranges.every(range => blockRanges.has(range))
        && [...blockRanges].every(range => ranges.includes(range));
    }
  }
  return resolved ? null : { ...value, uncertain: true };
};

export const buildProductPowerSupplyDescription = (specs: Record<string, unknown>, productKind?: string): string => {
  const value = (key: string): unknown => {
    // Imported legacy keys are normalized on the server on the next catalog edit.
    // Read them here as well so existing catalog rows work immediately.
    const alias = [...(aliases[key] || [])].reverse().find(name => specs[name] != null);
    return alias ? specs[alias] : specs[key];
  };
  const fieldSupply = (key: string): Supply | null => {
    const known = [...new Map([key, ...(aliases[key] || [])]
      .map(name => supply(specs[name])).filter((item): item is Supply => !!item)
      .map(item => [item.text, item])).values()];
    if (!known.length) return null;
    if (known.some(first => known.some(second => first !== second && !overlaps(first, second)))) {
      return { text: known.map(item => item.text).join(' / '), lower: Math.min(...known.map(item => item.lower)),
        upper: Math.max(...known.map(item => item.upper)), phase: null, uncertain: true, conflictingAliases: true };
    }
    return known.find(item => item.phase) || known[0]!;
  };
  const blocks: [string, Supply][] = [];
  for (const [label, key] of [['внутреннего блока', 'power_supply_indoor'], ['наружного блока', 'power_supply_outdoor']]) {
    const block = fieldSupply(key!);
    if (block) blocks.push([label!, block]);
  }
  const general = resolveBlockAggregate(fieldSupply('power_supply'), blocks);
  const voltage = resolveBlockAggregate(fieldSupply('power_supply_voltage'), blocks);
  const parts = blocks.map(([label, block]) => `параметры питания ${label}: ${display(block)}`);
  if (general && voltage && !overlaps(general, voltage)) {
    parts.push(`питание по общим данным: ${general.text} / ${voltage.text} (требует уточнения)`);
  } else {
    const common = general || voltage;
    const covered = common && blocks.some(([, block]) => overlaps(common, block)
      && (!common.phase || common.phase === block.phase)
      && (!common.text.includes('нейтраль') || block.text.includes('нейтраль'))
      && block.lower <= common.lower && common.upper <= block.upper);
    if (common && !covered) {
      const label = blocks.length ? 'питание по общим данным' : 'питание';
      const uncertain = blocks.length && !blocks.some(([, block]) => overlaps(common, block));
      parts.push(`${label}: ${display(common)}${uncertain && !common.uncertain ? ' (требует уточнения)' : ''}`);
    }
  }
  if (parts.length) {
    const location = String(value('power_supply_location') || '').toLowerCase();
    const indoor = /внутр/.test(location);
    const outdoor = /наруж|внешн|нруж/.test(location);
    if (indoor || outdoor) {
      const target = indoor && outdoor ? 'к внутреннему и наружному блокам'
        : indoor ? 'к внутреннему блоку' : 'к наружному блоку';
      parts.push(`подключение питания: ${target}`);
    }
  }
  if (!parts.length) {
    const kind = productKind || String(specs.product_kind || 'unknown');
    const airConditioner = ['complete_split_system', 'indoor_unit', 'outdoor_unit'].includes(kind)
      || (!['accessory', 'consumable', 'panel'].includes(kind) && (
        ['сплит-система', 'мульти-сплит-система', 'полупромышленный кондиционер', 'внутренний блок', 'наружный блок'].includes(String(specs.type || ''))
        || ['wall', 'cassette', 'duct', 'floor_ceiling', 'column', 'console'].includes(String(specs.indoor_type_kind || ''))
      ));
    if (airConditioner) return 'питание: уточняется';
  }
  return parts.join('; ');
};
