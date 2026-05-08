<script setup>
import { computed, onMounted, ref } from 'vue';
import ProductCard from './ProductCard.vue';
import { getCatalog, getFiltersConfig, resolveImageUrl } from '../utils/api';
import { getBrandConfig } from '../utils/brands';

const BASE_LIMIT = 20;
const POPULAR_LIMIT = 80;
const CATALOG_DEFAULT_SORT = 'recommended';
const CATEGORY_SLUG_LIST = ['cat-household', 'cat-multi', 'cat-industrial'];
const POWER_PRESETS = [
  { key: 'area-20', title: 'до 20 м²', min: null, max: 20 },
  { key: 'area-25', title: 'до 25 м²', min: null, max: 25 },
  { key: 'area-35', title: 'до 35 м²', min: null, max: 35 },
  { key: 'area-50', title: 'до 50 м²', min: null, max: 50 },
  { key: 'area-70', title: 'до 70 м²', min: null, max: 70 },
];
const INDUSTRIAL_TYPE_OPTIONS = [
  { value: 'duct', title: 'Канальные' },
  { value: 'cassette', title: 'Кассетные' },
  { value: 'floor_ceiling', title: 'Напольно-потолочные' },
  { value: 'column', title: 'Колонные' },
];
const CATEGORY_SLUGS = new Set(CATEGORY_SLUG_LIST);

const props = defineProps({
  initialProducts: {
    type: Array,
    default: () => []
  },
  initialMeta: {
    type: Object,
    default: () => ({ total: 0, page: 1, limit: BASE_LIMIT, pages: 1 })
  },
  initialPopularProducts: {
    type: Array,
    default: () => []
  },
  initialFilters: {
    type: Object,
    default: () => ({})
  },
  forcedTitle: {
    type: String,
    default: ''
  },
  forcedDescription: {
    type: String,
    default: ''
  },
  lockedInitialFilters: {
    type: Object,
    default: null
  },
  initialCategorySlug: {
    type: String,
    default: 'cat-household'
  },
  initialBrands: {
    type: Array,
    default: () => []
  }
});

const initialActiveTags = Array.isArray(props.lockedInitialFilters?.tag_slugs)
  ? [...props.lockedInitialFilters.tag_slugs]
  : [props.initialCategorySlug || 'cat-household'];
const products = ref(props.initialProducts || []);
const popularProducts = ref(props.initialPopularProducts || []);
const meta = ref(props.initialMeta || { total: 0, page: 1, limit: BASE_LIMIT, pages: 1 });

const loadingInitial = ref(false);
const loadingMore = ref(false);
const loadingBrands = ref(false);
const dynamicActive = ref(false);

const activeTags = ref([...new Set(initialActiveTags)]);
const searchQuery = ref('');
const sort = ref(props.initialFilters?.sort || CATALOG_DEFAULT_SORT);
const mobileSearchOpen = ref(false);
const advancedFiltersOpen = ref(false);

const currentAreaMin = ref(props.initialFilters?.area_min ?? null);
const currentAreaMax = ref(props.initialFilters?.area_max ?? null);
const currentIsInverter = ref(props.initialFilters?.is_inverter ?? null);
const currentHasWifi = ref(props.initialFilters?.has_wifi ?? null);
const currentHasFreshAir = ref(props.initialFilters?.has_fresh_air ?? null);
const currentHeatingMin = ref(props.initialFilters?.heating_min ?? null);
const currentIndoorTypes = ref([...(props.initialFilters?.indoor_types || [])]);
const selectedOutdoorSlug = ref('');
const selectedIndoorQuantities = ref({});

const availableBrands = ref((props.initialBrands || []).map((brand) => ({
  ...brand,
  sort_order: brand.sort_order ?? 999,
})));
let searchDebounceTimeout = null;

const getBrandLogo = (brand) => {
  const logoUrl = String(brand?.logo_url || '').trim();
  if (logoUrl) return resolveImageUrl(logoUrl);
  return getBrandConfig(brand?.slug || '').logo || '';
};

const lockedFilters = computed(() => props.lockedInitialFilters || null);
const knownBrandSlugs = computed(() => new Set(availableBrands.value.map((brand) => brand.slug)));
const activeCategorySlug = computed(() => activeTags.value.find((slug) => CATEGORY_SLUGS.has(slug)) || null);
const activeBrandSlug = computed(() => activeTags.value.find((slug) => knownBrandSlugs.value.has(slug)) || null);
const isHouseholdCategory = computed(() => activeCategorySlug.value === 'cat-household');
const isIndustrialCategory = computed(() => activeCategorySlug.value === 'cat-industrial');
const isMultiCategory = computed(() => activeCategorySlug.value === 'cat-multi');

const isCatalogAvailable = (product) => {
  const status = String(product?.availability_status || '');
  const qty = Number(product?.vitebsk_qty || 0) + Number(product?.minsk_qty || 0);
  return qty > 0 || status === 'in_stock_now' || status === 'available_2_3_days';
};

const getSpecValue = (product, keys = []) => {
  if (!product) return null;
  const specs = product.specs || {};
  for (const key of keys) {
    if (specs[key] !== undefined && specs[key] !== null && String(specs[key]).trim() !== '') {
      return specs[key];
    }
  }
  return null;
};

const parseNumber = (value) => {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const match = String(value).replace(',', '.').match(/[-+]?\d+(?:\.\d+)?/);
  if (!match) return null;
  const parsed = Number.parseFloat(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
};

const normalizeText = (value) => String(value || '').toLowerCase().replace(/ё/g, 'е');
const normalizeBrand = (value) => normalizeText(value).replace(/[^a-z0-9а-я]/g, '');
const isSameBrand = (left, right) => {
  const a = normalizeBrand(left);
  const b = normalizeBrand(right);
  return Boolean(a) && Boolean(b) && a === b;
};
const parseSlugList = (value) => {
  if (Array.isArray(value)) {
    return Array.from(new Set(value.map((item) => String(item || '').trim()).filter(Boolean)));
  }
  if (typeof value === 'string') {
    return Array.from(new Set(
      value.split(/[,\n;]/g).map((item) => item.trim()).filter(Boolean),
    ));
  }
  return [];
};
const normalizeCapacityToken = (value) => {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const numeric = raw.replace(',', '.').match(/\d+(?:\.\d+)?/);
  if (!numeric) return '';
  let parsed = Number.parseFloat(numeric[0]);
  if (!Number.isFinite(parsed) || parsed <= 0) return '';
  if (parsed >= 1000) parsed = parsed / 1000;
  return String(Math.max(1, Math.round(parsed))).padStart(2, '0');
};
const normalizeCapacityCombo = (value) => {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const tokens = raw
    .split('+')
    .map((item) => normalizeCapacityToken(item))
    .filter(Boolean)
    .sort((a, b) => Number(a) - Number(b));
  return tokens.join('+');
};
const parseCapacityCombos = (value) => {
  const chunks = Array.isArray(value)
    ? value.map((item) => String(item ?? ''))
    : String(value ?? '').split(/[,\n;]/g).map((item) => item.trim());
  const unique = new Set();
  chunks.forEach((chunk) => {
    const normalized = normalizeCapacityCombo(chunk);
    if (normalized) unique.add(normalized);
  });
  return Array.from(unique);
};
const getCapacityClassFromKw = (kw) => {
  if (!Number.isFinite(kw) || kw <= 0) return '';
  const approx = kw * 3.412;
  const standards = [7, 9, 12, 18, 24, 30, 36, 42, 48, 60];
  let nearest = standards[0];
  let best = Number.POSITIVE_INFINITY;
  standards.forEach((candidate) => {
    const diff = Math.abs(candidate - approx);
    if (diff < best) {
      best = diff;
      nearest = candidate;
    }
  });
  return String(nearest).padStart(2, '0');
};
const toPositiveInt = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(1, Math.floor(parsed));
};
const normalizeRuleLines = (lines) => {
  if (!Array.isArray(lines)) return [];
  const merged = new Map();
  lines.forEach((line) => {
    if (!line) return;
    if (typeof line === 'string') {
      const [slugRaw, qtyRaw] = line.split(':');
      const slug = String(slugRaw || '').trim();
      if (!slug) return;
      merged.set(slug, Number(merged.get(slug) || 0) + toPositiveInt(qtyRaw || 1));
      return;
    }
    if (typeof line !== 'object') return;
    const slug = String(line.slug ?? line.indoor_slug ?? line.model_slug ?? '').trim();
    if (!slug) return;
    const qty = toPositiveInt(line.qty ?? line.quantity ?? line.count ?? 1);
    merged.set(slug, Number(merged.get(slug) || 0) + qty);
  });
  return Array.from(merged.entries()).map(([slug, qty]) => ({ slug, qty }));
};
const getComboSignature = (lines) => normalizeRuleLines(lines)
  .sort((a, b) => a.slug.localeCompare(b.slug, 'ru'))
  .map((line) => `${line.slug}:${line.qty}`)
  .join('|');
const parseMultiComboRules = (value) => {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const lines = normalizeRuleLines(item.lines ?? item.items ?? []);
      if (lines.length === 0) return null;
      const title = String(item.title ?? item.name ?? '').trim();
      return {
        title,
        lines,
        signature: getComboSignature(lines),
      };
    })
    .filter(Boolean);
};
const formatComboRule = (rule) => (
  String(rule?.title || '').trim()
  || rule.lines.map((line) => `${line.qty}×${line.slug}`).join(' + ')
);

const getProductBrand = (product) => {
  const fromSpecs = getSpecValue(product, ['brand', 'Бренд', 'Марка', 'Производитель']);
  if (fromSpecs) return String(fromSpecs).trim();
  const brandTag = (product?.tags || []).find((tag) => (tag.group?.slug || tag.group_slug) === 'brand');
  return brandTag?.title || '';
};

const getProductBrandSlug = (product) => {
  const brandTag = (product?.tags || []).find((tag) => (tag.group?.slug || tag.group_slug) === 'brand');
  if (brandTag?.slug) return String(brandTag.slug).trim().toLowerCase();
  const brandTitle = getProductBrand(product);
  const matched = availableBrands.value.find((brand) => isSameBrand(brand.title, brandTitle));
  return matched?.slug || normalizeBrand(brandTitle);
};

const brandPriorityIndex = (brandSlug) => {
  const configuredIndex = availableBrands.value.findIndex((brand) => brand.slug === brandSlug);
  return configuredIndex >= 0 ? configuredIndex : availableBrands.value.length + 50;
};

const popularAreaLimit = computed(() => {
  const selectedMax = Number(currentAreaMax.value || 0);
  return selectedMax > 0 ? selectedMax : 35;
});

const diversifyPopularModels = (items, limit = 8) => {
  const candidates = items.filter((product) => (
    isCatalogAvailable(product) && Number(product?.area || 0) <= popularAreaLimit.value
  ));
  const groups = new Map();
  candidates.forEach((product) => {
    const brandSlug = getProductBrandSlug(product) || 'unknown';
    const compressor = product?.is_inverter ? 'inverter' : 'onoff';
    const key = `${brandSlug}:${compressor}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        brandSlug,
        compressor,
        items: [],
      });
    }
    groups.get(key).items.push(product);
  });

  const compressorOrder = { onoff: 0, inverter: 1 };
  const orderedGroups = [...groups.values()].sort((a, b) => (
    brandPriorityIndex(a.brandSlug) - brandPriorityIndex(b.brandSlug)
    || (compressorOrder[a.compressor] ?? 9) - (compressorOrder[b.compressor] ?? 9)
    || a.brandSlug.localeCompare(b.brandSlug, 'ru')
  ));

  const result = [];
  let cursor = 0;
  while (result.length < limit && orderedGroups.some((group) => cursor < group.items.length)) {
    orderedGroups.forEach((group) => {
      if (result.length < limit && group.items[cursor]) {
        result.push(group.items[cursor]);
      }
    });
    cursor += 1;
  }
  return result;
};

const popularModels = computed(() => diversifyPopularModels(popularProducts.value, 8));

const showPopularModels = computed(() => (
  isHouseholdCategory.value
  && !loadingInitial.value
  && popularModels.value.length >= 3
));

const getCoolingKw = (product) => parseNumber(getSpecValue(product, ['capacity_cooling_kw', 'Мощность охлаждения']));
const getIndoorCapacityClass = (product) => {
  const direct = normalizeCapacityToken(getSpecValue(product, [
    'capacity_class',
    'btu_class',
    'BTU класс',
    'Класс BTU',
    'BTU',
    'БТЕ',
    'Мощность BTU',
  ]));
  if (direct) return direct;
  const kw = getCoolingKw(product);
  const fromKw = getCapacityClassFromKw(kw);
  if (fromKw) return fromKw;
  const titleMatch = String(product?.title || '').match(/\b(07|09|12|18|24|30|36|42|48|60)\b/);
  return titleMatch?.[1] || '';
};

const isIndoorUnit = (product) => {
  const typeText = normalizeText(getSpecValue(product, ['type', 'Тип']));
  const titleText = normalizeText(product?.title);
  return typeText.includes('внутрен') || titleText.includes('внутренний блок');
};

const isOutdoorUnit = (product) => {
  if (isIndoorUnit(product)) return false;
  const typeText = normalizeText(getSpecValue(product, ['type', 'Тип']));
  const titleText = normalizeText(product?.title);
  return typeText.includes('мульти') || typeText.includes('наруж') || titleText.includes('мульти-сплит');
};

const getOutdoorPortsMax = (product) => parseNumber(
  getSpecValue(product, ['multi_max_indoor_units', 'Максимальное количество внутренних блоков'])
);

const multiOutdoorOptions = computed(() => products.value.filter((product) => isOutdoorUnit(product)));
const multiIndoorOptions = computed(() => products.value.filter((product) => isIndoorUnit(product)));

const selectedOutdoorUnit = computed(
  () => multiOutdoorOptions.value.find((product) => product.slug === selectedOutdoorSlug.value) || null
);
const selectedOutdoorCompatMode = computed(() => (
  String(getSpecValue(selectedOutdoorUnit.value, ['multi_compat_mode']) || '').trim().toLowerCase() === 'strict'
    ? 'strict'
    : 'free_match'
));
const selectedOutdoorCompatibleIndoorSlugs = computed(() => new Set(
  parseSlugList(getSpecValue(selectedOutdoorUnit.value, ['compatible_indoor_slugs'])),
));
const selectedOutdoorComboRules = computed(() => (
  parseMultiComboRules(getSpecValue(selectedOutdoorUnit.value, ['multi_combo_rules']))
));
const selectedOutdoorCapacityCombos = computed(() => (
  parseCapacityCombos(getSpecValue(selectedOutdoorUnit.value, ['multi_capacity_combos']))
));
const hasOutdoorBrandRestriction = computed(() => Boolean(normalizeBrand(getProductBrand(selectedOutdoorUnit.value))));
const hasOutdoorCompatRestriction = computed(() => selectedOutdoorCompatibleIndoorSlugs.value.size > 0);
const hasOutdoorStrictComboRestriction = computed(() => (
  selectedOutdoorCompatMode.value === 'strict' && selectedOutdoorComboRules.value.length > 0
));
const hasOutdoorCapacityComboRestriction = computed(() => (
  selectedOutdoorCompatMode.value === 'free_match' && selectedOutdoorCapacityCombos.value.length > 0
));
const multiIndoorOptionsFiltered = computed(() => {
  let result = [...multiIndoorOptions.value];
  const selectedBrand = getProductBrand(selectedOutdoorUnit.value);
  if (selectedBrand) {
    result = result.filter((product) => isSameBrand(getProductBrand(product), selectedBrand));
  }
  if (hasOutdoorCompatRestriction.value) {
    result = result.filter((product) => selectedOutdoorCompatibleIndoorSlugs.value.has(product.slug));
  }
  return result;
});

const selectedIndoorRows = computed(() => multiIndoorOptionsFiltered.value
  .map((product) => ({
    product,
    qty: Number(selectedIndoorQuantities.value[product.slug] || 0),
    brand: getProductBrand(product),
    coolingKw: getCoolingKw(product),
  }))
  .filter((row) => row.qty > 0));

const selectedIndoorCount = computed(
  () => selectedIndoorRows.value.reduce((sum, row) => sum + row.qty, 0)
);
const indoorCoolingSum = computed(
  () => selectedIndoorRows.value.reduce((sum, row) => sum + ((row.coolingKw || 0) * row.qty), 0)
);
const outdoorPortsMax = computed(() => getOutdoorPortsMax(selectedOutdoorUnit.value));
const outdoorCoolingKw = computed(() => getCoolingKw(selectedOutdoorUnit.value));
const outdoorBrand = computed(() => getProductBrand(selectedOutdoorUnit.value));
const allowedCoolingLimit = computed(() => (
  outdoorCoolingKw.value ? Number((outdoorCoolingKw.value * 1.3).toFixed(2)) : null
));
const brandMismatchCount = computed(() => selectedIndoorRows.value.filter((row) => (
  outdoorBrand.value
  && row.brand
  && !isSameBrand(row.brand, outdoorBrand.value)
)).length);
const selectedIndoorSignature = computed(() => getComboSignature(
  selectedIndoorRows.value.map((row) => ({
    slug: String(row.product?.slug || ''),
    qty: Number(row.qty || 0),
  })),
));
const selectedIndoorCapacityTokens = computed(() => {
  const tokens = [];
  selectedIndoorRows.value.forEach((row) => {
    const klass = getIndoorCapacityClass(row.product);
    if (!klass) return;
    const qty = Math.max(0, Number(row.qty || 0));
    for (let idx = 0; idx < qty; idx += 1) {
      tokens.push(klass);
    }
  });
  return tokens.sort((a, b) => Number(a) - Number(b));
});
const selectedIndoorMissingCapacityCount = computed(() => (
  selectedIndoorRows.value.filter((row) => !getIndoorCapacityClass(row.product)).length
));
const selectedIndoorCapacitySignature = computed(() => (
  selectedIndoorCapacityTokens.value.join('+')
));
const matchedComboRule = computed(() => (
  selectedOutdoorComboRules.value.find((rule) => rule.signature === selectedIndoorSignature.value) || null
));
const matchedCapacityCombo = computed(() => (
  selectedOutdoorCapacityCombos.value.find((combo) => combo === selectedIndoorCapacitySignature.value) || ''
));
const multiIndoorFilterHint = computed(() => {
  const messages = [];
  if (hasOutdoorBrandRestriction.value && outdoorBrand.value) {
    messages.push(`Показаны внутренние блоки бренда ${outdoorBrand.value}.`);
  }
  if (hasOutdoorCompatRestriction.value) {
    messages.push('Дополнительно применен список явной совместимости для выбранного наружного.');
  }
  if (hasOutdoorStrictComboRestriction.value) {
    messages.push('Режим strict: доступны только заранее заданные конфигурации конкретных моделей.');
  }
  if (hasOutdoorCapacityComboRestriction.value) {
    messages.push('Режим free match: проверяем комбинацию по мощностным классам (09+12 и т.д.).');
  }
  return messages.join(' ');
});

const multiValidationHint = computed(() => {
  if (hasOutdoorStrictComboRestriction.value) return 'v3 strict: exact slug-конфигурации + порты/бренд';
  if (hasOutdoorCapacityComboRestriction.value) return 'v3 free match: таблица мощностей + порты/бренд';
  return 'v2: порты/мощность/бренд';
});

const multiValidation = computed(() => {
  const reasons = [];
  if (!selectedOutdoorUnit.value) {
    reasons.push('Выберите наружный блок.');
  }
  if (selectedIndoorCount.value <= 0) {
    reasons.push('Добавьте хотя бы один внутренний блок.');
  }
  if (outdoorPortsMax.value && selectedIndoorCount.value > outdoorPortsMax.value) {
    reasons.push(`Превышен лимит портов: ${selectedIndoorCount.value} из ${outdoorPortsMax.value}.`);
  }
  const shouldCheckCoolingLimit = !hasOutdoorStrictComboRestriction.value && !hasOutdoorCapacityComboRestriction.value;
  if (shouldCheckCoolingLimit && allowedCoolingLimit.value && indoorCoolingSum.value > allowedCoolingLimit.value + 0.001) {
    reasons.push(
      `Суммарная мощность внутренних (${indoorCoolingSum.value.toFixed(1)} кВт) выше лимита `
      + `(${allowedCoolingLimit.value.toFixed(1)} кВт).`
    );
  }
  if (brandMismatchCount.value > 0) {
    reasons.push('В конфигурации смешаны бренды. Для подбора поддерживается один бренд.');
  }
  if (hasOutdoorCompatRestriction.value && selectedIndoorCount.value === 0) {
    reasons.push('Для выбранного наружного блока добавьте совместимые внутренние блоки из списка ниже.');
  }
  if (hasOutdoorStrictComboRestriction.value && selectedIndoorCount.value > 0 && !matchedComboRule.value) {
    reasons.push('Выбранная комбинация не входит в строгие допустимые конфигурации.');
  }
  if (hasOutdoorCapacityComboRestriction.value && selectedIndoorCount.value > 0) {
    if (selectedIndoorMissingCapacityCount.value > 0) {
      reasons.push('Для части внутренних блоков не удалось определить мощностной класс (09/12/18).');
    } else if (!matchedCapacityCombo.value) {
      reasons.push('Выбранная комбинация не входит в допустимую таблицу free match.');
    }
  }
  const matchedConfigText = matchedComboRule.value
    ? formatComboRule(matchedComboRule.value)
    : matchedCapacityCombo.value;
  return {
    isValid: reasons.length === 0,
    reasons,
    summary: selectedOutdoorUnit.value
      ? `Наружный блок: ${selectedOutdoorUnit.value.title}. `
        + `Внутренних блоков: ${selectedIndoorCount.value}. `
        + `Суммарная мощность: ${indoorCoolingSum.value.toFixed(1)} кВт.`
        + (matchedConfigText ? ` Конфигурация: ${matchedConfigText}.` : '')
      : 'Выберите наружный блок и добавьте внутренние блоки.',
  };
});

const multiLeadUrl = computed(() => {
  if (!selectedOutdoorUnit.value) return '/contacts';
  const sp = new URLSearchParams();
  sp.set('topic', 'multi_split');
  sp.set('outdoor', selectedOutdoorUnit.value.slug);
  sp.set(
    'indoors',
    selectedIndoorRows.value
      .map((row) => `${row.product.slug}:${row.qty}`)
      .join(','),
  );
  return `/contacts?${sp.toString()}`;
});

const formatKw = (value) => {
  if (!Number.isFinite(value)) return '—';
  return String(Number(value).toFixed(1)).replace('.0', '');
};

const syncMultiSelectionState = () => {
  const outdoorSlugs = new Set(multiOutdoorOptions.value.map((product) => product.slug));
  const indoorSlugs = new Set(multiIndoorOptionsFiltered.value.map((product) => product.slug));

  if (outdoorSlugs.size > 0 && !outdoorSlugs.has(selectedOutdoorSlug.value)) {
    selectedOutdoorSlug.value = multiOutdoorOptions.value[0].slug;
  }
  if (outdoorSlugs.size === 0) {
    selectedOutdoorSlug.value = '';
  }

  const nextQuantities = {};
  Object.entries(selectedIndoorQuantities.value || {}).forEach(([slug, qty]) => {
    const count = Number(qty || 0);
    if (indoorSlugs.has(slug) && count > 0) {
      nextQuantities[slug] = count;
    }
  });
  selectedIndoorQuantities.value = nextQuantities;
};

const activePowerPresetKey = computed(() => {
  const min = currentAreaMin.value === null || currentAreaMin.value === undefined || currentAreaMin.value === ''
    ? null
    : Number(currentAreaMin.value);
  const max = currentAreaMax.value === null || currentAreaMax.value === undefined || currentAreaMax.value === ''
    ? null
    : Number(currentAreaMax.value);
  const found = POWER_PRESETS.find((preset) => preset.min === min && preset.max === max);
  return found?.key || null;
});

const hasActiveAdvancedFilters = computed(() => (
  sort.value !== CATALOG_DEFAULT_SORT
  || currentIsInverter.value !== null
  || currentHasWifi.value !== null
  || currentHasFreshAir.value !== null
  || currentHeatingMin.value !== null
));

const pageTitle = computed(() => {
  if (props.forcedTitle) return props.forcedTitle;
  if (activeCategorySlug.value === 'cat-multi') return 'Мульти-сплит системы';
  if (activeCategorySlug.value === 'cat-industrial') return 'Полупромышленные кондиционеры';
  return 'Бытовые кондиционеры';
});

const pageDescription = computed(() => {
  if (props.forcedDescription) return props.forcedDescription;
  if (activeCategorySlug.value === 'cat-multi') {
    return 'Системы с одним наружным блоком и несколькими внутренними для гибкого зонирования.';
  }
  if (activeCategorySlug.value === 'cat-industrial') {
    return 'Кассетные, канальные и напольно-потолочные решения для коммерческих и сложных объектов.';
  }
  return 'Настенные сплит-системы для квартиры и дома с удобной фильтрацией по брендам.';
});

const semiGuideUrl = '/blog/polupromyshlennye-kondicionery-tipy-i-vybor';

const hasMore = computed(() => {
  const currentPage = Number(meta.value?.page || 1);
  const totalPages = Number(meta.value?.pages || 1);
  return currentPage < totalPages;
});

const getParamsFromUrl = () => {
  if (typeof window === 'undefined') return null;
  const sp = new URLSearchParams(window.location.search);

  const tags = [];
  sp.getAll('tag_slugs').forEach((value) => {
    value.split(',').forEach((tag) => {
      const clean = tag.trim();
      if (clean) tags.push(clean);
    });
  });

  return {
    page: Number.parseInt(sp.get('page') || '1', 10) || 1,
    sort: sp.get('sort') || CATALOG_DEFAULT_SORT,
    q: sp.get('q') || '',
    tag_slugs: tags,
    area_min: sp.get('area_min') || null,
    area_max: sp.get('area_max') || null,
    is_inverter: sp.get('is_inverter') === 'true'
      ? true
      : sp.get('is_inverter') === 'false'
        ? false
        : null,
    has_wifi: sp.get('has_wifi') === 'true'
      ? true
      : sp.get('has_wifi') === 'false'
        ? false
        : null,
    has_fresh_air: sp.get('has_fresh_air') === 'true'
      ? true
      : sp.get('has_fresh_air') === 'false'
        ? false
        : null,
    indoor_types: sp.getAll('indoor_types').flatMap((value) => value.split(',')).map((v) => v.trim()).filter(Boolean),
    heating_min: sp.get('heating_min') || null,
  };
};

const applyLockedFilters = (params) => {
  if (!lockedFilters.value) return params;

  const merged = { ...params };
  const lockedTagSlugs = Array.isArray(lockedFilters.value.tag_slugs)
    ? lockedFilters.value.tag_slugs
    : [];

  merged.tag_slugs = [...new Set([...(params.tag_slugs || []), ...lockedTagSlugs])];

  const scalarKeys = [
    'area_min',
    'area_max',
    'is_inverter',
    'has_wifi',
    'has_fresh_air',
    'heating_min',
    'sort',
  ];

  scalarKeys.forEach((key) => {
    if (lockedFilters.value[key] !== undefined && lockedFilters.value[key] !== null) {
      merged[key] = lockedFilters.value[key];
    }
  });

  return merged;
};

const syncStateFromUrl = () => {
  const rawParams = getParamsFromUrl();
  if (!rawParams) return;
  const params = applyLockedFilters(rawParams);

  activeTags.value = [...params.tag_slugs];
  searchQuery.value = params.q;
  sort.value = params.sort;

  currentAreaMin.value = params.area_min;
  currentAreaMax.value = params.area_max;
  currentIsInverter.value = params.is_inverter;
  currentHasWifi.value = params.has_wifi;
  currentHasFreshAir.value = params.has_fresh_air;
  currentIndoorTypes.value = [...params.indoor_types];
  currentHeatingMin.value = params.heating_min;

  if (!activeTags.value.some((slug) => CATEGORY_SLUGS.has(slug))) {
    const lockedCategory = (Array.isArray(lockedFilters.value?.tag_slugs)
      ? lockedFilters.value.tag_slugs
      : []
    ).find((slug) => CATEGORY_SLUGS.has(slug));

    activeTags.value.push(lockedCategory || 'cat-household');
  }
};

const hasUrlQueryParams = () => {
  if (typeof window === 'undefined') return false;
  return Array.from(new URLSearchParams(window.location.search).keys()).length > 0;
};

const getUrlPage = () => {
  if (typeof window === 'undefined') return 1;
  const parsed = Number.parseInt(new URLSearchParams(window.location.search).get('page') || '1', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
};

const syncStaticHeaderFromState = () => {
  if (typeof document === 'undefined') return;

  const header = document.querySelector('.catalog-page > .catalog-header');
  if (!header) return;

  const title = header.querySelector('h1');
  const description = header.querySelector('.header-description');
  if (title) title.textContent = pageTitle.value;
  if (description) description.textContent = pageDescription.value;
};

const buildApiParams = (page = 1) => {
  const base = {
    page,
    limit: BASE_LIMIT,
    sort: sort.value,
    tag_slugs: [...activeTags.value],
    q: searchQuery.value.trim() || undefined,
    area_min: currentAreaMin.value || undefined,
    area_max: currentAreaMax.value || undefined,
    is_inverter: currentIsInverter.value,
    has_wifi: currentHasWifi.value,
    has_fresh_air: currentHasFreshAir.value,
    indoor_types: isIndustrialCategory.value ? [...currentIndoorTypes.value] : undefined,
    heating_min: currentHeatingMin.value || undefined,
  };

  return applyLockedFilters(base);
};

const buildPopularApiParams = () => ({
  ...buildApiParams(1),
  page: 1,
  limit: POPULAR_LIMIT,
  sort: CATALOG_DEFAULT_SORT,
});

const syncUrlFromState = (page = 1, { replace = false } = {}) => {
  if (typeof window === 'undefined') return;

  const params = buildApiParams(page);
  const sp = new URLSearchParams();

  if (params.tag_slugs && params.tag_slugs.length > 0) {
    sp.set('tag_slugs', params.tag_slugs.join(','));
  }
  if (page > 1) sp.set('page', String(page));
  if (params.sort && params.sort !== CATALOG_DEFAULT_SORT) sp.set('sort', params.sort);
  if (params.q) sp.set('q', params.q);

  if (params.area_min !== undefined) sp.set('area_min', String(params.area_min));
  if (params.area_max !== undefined) sp.set('area_max', String(params.area_max));
  if (params.is_inverter !== null && params.is_inverter !== undefined) sp.set('is_inverter', String(params.is_inverter));
  if (params.has_wifi !== null && params.has_wifi !== undefined) sp.set('has_wifi', String(params.has_wifi));
  if (params.has_fresh_air !== null && params.has_fresh_air !== undefined) sp.set('has_fresh_air', String(params.has_fresh_air));
  if (params.indoor_types && params.indoor_types.length > 0) {
    params.indoor_types.forEach((value) => sp.append('indoor_types', value));
  }
  if (params.heating_min !== undefined) sp.set('heating_min', String(params.heating_min));

  const query = sp.toString();
  const newUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
  if (replace) {
    window.history.replaceState({}, '', newUrl);
  } else {
    window.history.pushState({}, '', newUrl);
  }
};

const activateDynamicResults = () => {
  dynamicActive.value = true;
};

const fetchProducts = async ({ page = 1, append = false } = {}) => {
  activateDynamicResults();
  syncStaticHeaderFromState();
  if (append) {
    loadingMore.value = true;
  } else {
    loadingInitial.value = true;
  }

  try {
    const apiParams = buildApiParams(page);
    const [data, popularData] = append
      ? [await getCatalog(apiParams), null]
      : await Promise.all([
        getCatalog(apiParams),
        getCatalog(buildPopularApiParams()),
      ]);

    const incomingItems = data.items || [];
    if (append) {
      const seen = new Set(products.value.map((item) => item.id));
      const merged = [...products.value];
      incomingItems.forEach((item) => {
        if (!seen.has(item.id)) {
          merged.push(item);
          seen.add(item.id);
        }
      });
      products.value = merged;
    } else {
      products.value = incomingItems;
      popularProducts.value = popularData?.items || incomingItems;
    }

    syncMultiSelectionState();

    meta.value = data.meta || { total: 0, page: 1, limit: BASE_LIMIT, pages: 1 };
  } catch (error) {
    console.error('Fetch catalog failed', error);
  } finally {
    loadingInitial.value = false;
    loadingMore.value = false;
  }
};

const updateBrandsFallbackFromProducts = () => {
  if (availableBrands.value.length > 0) return;

  const acc = new Map();
  products.value.forEach((product) => {
    const brandTag = (product.tags || []).find((tag) =>
      (tag.group?.slug === 'brand' || tag.group_slug === 'brand') && tag.slug
    );
    if (!brandTag) return;

    if (!acc.has(brandTag.slug)) {
      acc.set(brandTag.slug, {
        slug: brandTag.slug,
        title: brandTag.title,
        sort_order: brandTag.sort_order ?? 999,
      });
    }
  });

  availableBrands.value = [...acc.values()].sort((a, b) => {
    if ((a.sort_order ?? 999) !== (b.sort_order ?? 999)) {
      return (a.sort_order ?? 999) - (b.sort_order ?? 999);
    }
    return (a.title || '').localeCompare(b.title || '');
  });
};

const loadBrands = async () => {
  if (availableBrands.value.length > 0) {
    updateBrandsFallbackFromProducts();
    return;
  }
  loadingBrands.value = true;
  try {
    const filters = await getFiltersConfig();
    availableBrands.value = (filters?.brands || []).map((brand) => ({
      ...brand,
      sort_order: brand.sort_order ?? 999,
    }));
  } catch (error) {
    console.error('Failed to load brands', error);
  } finally {
    loadingBrands.value = false;
    updateBrandsFallbackFromProducts();
  }
};

const setCategory = async (categorySlug) => {
  activeTags.value = activeTags.value.filter((slug) => !CATEGORY_SLUGS.has(slug));
  activeTags.value.push(categorySlug);
  if (categorySlug !== 'cat-household') {
    currentAreaMin.value = null;
    currentAreaMax.value = null;
  }
  if (categorySlug !== 'cat-industrial') {
    currentIndoorTypes.value = [];
  }
  if (categorySlug !== 'cat-multi') {
    selectedOutdoorSlug.value = '';
    selectedIndoorQuantities.value = {};
  }

  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};
const toggleIndustrialType = async (value) => {
  if (!isIndustrialCategory.value) return;
  const set = new Set(currentIndoorTypes.value);
  if (set.has(value)) {
    set.delete(value);
  } else {
    set.add(value);
  }
  currentIndoorTypes.value = [...set];
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const clearIndustrialTypes = async () => {
  currentIndoorTypes.value = [];
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const selectMultiOutdoor = (slug) => {
  selectedOutdoorSlug.value = slug;
};

const changeIndoorQty = (slug, delta) => {
  if (!isMultiCategory.value) return;
  if (!multiIndoorOptionsFiltered.value.some((item) => item.slug === slug)) return;
  const next = { ...selectedIndoorQuantities.value };
  const current = Number(next[slug] || 0);
  const updated = Math.max(0, current + delta);
  if (updated <= 0) {
    delete next[slug];
  } else {
    next[slug] = updated;
  }
  selectedIndoorQuantities.value = next;
};

const clearMultiConfig = () => {
  selectedIndoorQuantities.value = {};
  selectedOutdoorSlug.value = multiOutdoorOptions.value[0]?.slug || '';
};

const toggleBrand = async (brandSlug) => {
  const brandSet = knownBrandSlugs.value;
  if (brandSlug === '__all__') {
    activeTags.value = activeTags.value.filter((slug) => !brandSet.has(slug));
    syncUrlFromState(1);
    await fetchProducts({ page: 1, append: false });
    return;
  }

  const isActive = activeBrandSlug.value === brandSlug;

  activeTags.value = activeTags.value.filter((slug) => !brandSet.has(slug));
  if (!isActive) {
    activeTags.value.push(brandSlug);
  }

  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const loadMore = async () => {
  if (!hasMore.value || loadingMore.value) return;
  const nextPage = Number(meta.value?.page || 1) + 1;
  syncUrlFromState(nextPage);
  await fetchProducts({ page: nextPage, append: true });
};

const setPowerPreset = async (preset) => {
  if (activePowerPresetKey.value === preset.key) {
    currentAreaMin.value = null;
    currentAreaMax.value = null;
  } else {
    currentAreaMin.value = preset.min;
    currentAreaMax.value = preset.max;
  }

  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const toggleBooleanFilter = async (key, value) => {
  const map = {
    is_inverter: currentIsInverter,
    has_wifi: currentHasWifi,
    has_fresh_air: currentHasFreshAir,
  };
  const target = map[key];
  if (!target) return;

  target.value = target.value === value ? null : value;
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const setHeatingMin = async (value) => {
  currentHeatingMin.value = currentHeatingMin.value === value ? null : value;
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const resetAdvancedFilters = async () => {
  sort.value = CATALOG_DEFAULT_SORT;
  currentIsInverter.value = null;
  currentHasWifi.value = null;
  currentHasFreshAir.value = null;
  currentIndoorTypes.value = [];
  currentHeatingMin.value = null;
  if (!isHouseholdCategory.value) {
    currentAreaMin.value = null;
    currentAreaMax.value = null;
  }
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const onSortChange = async () => {
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const onSearchInput = () => {
  if (searchDebounceTimeout) clearTimeout(searchDebounceTimeout);
  searchDebounceTimeout = setTimeout(async () => {
    syncUrlFromState(1, { replace: true });
    await fetchProducts({ page: 1, append: false });
  }, 450);
};

onMounted(async () => {
  syncStateFromUrl();
  syncStaticHeaderFromState();
  await loadBrands();
  syncMultiSelectionState();
  if (hasUrlQueryParams()) {
    await fetchProducts({ page: getUrlPage(), append: false });
  }
});
</script>

<template>
  <div class="catalog-shell">
    <section class="catalog-controls" aria-label="Фильтры каталога">
      <div class="controls-top">
        <div class="search-input-wrapper header-search">
        <span class="material-icons-round search-icon">search</span>
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Поиск по модели, бренду, характеристике"
          @input="onSearchInput"
        />
      </div>
        <a
          v-if="isIndustrialCategory"
          :href="semiGuideUrl"
          class="semi-guide-link"
        >
          Как выбрать тип полупромышленного кондиционера
        </a>
      </div>
    </section>

    <section v-if="isHouseholdCategory" class="glass-panel quick-power-panel">
      <div class="section-label">Мощность</div>
      <div class="quick-chip-row">
        <button
          class="quick-chip"
          :class="{ active: activePowerPresetKey === null }"
          @click="setPowerPreset({ key: '__all__', min: null, max: null })"
        >
          Любая
        </button>
        <button
          v-for="preset in POWER_PRESETS"
          :key="preset.key"
          class="quick-chip"
          :class="{ active: activePowerPresetKey === preset.key }"
          @click="setPowerPreset(preset)"
        >
          {{ preset.title }}
        </button>
      </div>
    </section>

    <section v-if="isIndustrialCategory" class="glass-panel quick-power-panel">
      <div class="section-label">Тип внутреннего блока</div>
      <div class="quick-chip-row">
        <button
          class="quick-chip"
          :class="{ active: currentIndoorTypes.length === 0 }"
          @click="clearIndustrialTypes"
        >
          Все типы
        </button>
        <button
          v-for="item in INDUSTRIAL_TYPE_OPTIONS"
          :key="item.value"
          class="quick-chip"
          :class="{ active: currentIndoorTypes.includes(item.value) }"
          @click="toggleIndustrialType(item.value)"
        >
          {{ item.title }}
        </button>
      </div>
    </section>

    <section v-if="isMultiCategory" class="glass-panel multi-config-panel">
      <div class="section-head">
        <div class="section-label">Подбор Мульти-Сплит</div>
        <div class="label-hint">{{ multiValidationHint }}</div>
      </div>

      <div v-if="multiOutdoorOptions.length === 0 || multiIndoorOptions.length === 0" class="multi-config-empty">
        Недостаточно данных для подбора. Для конфигуратора нужны и наружные, и внутренние блоки в категории.
      </div>

      <template v-else>
        <div class="multi-config-grid">
          <div class="multi-config-column">
            <div class="control-label">1. Наружный блок</div>
            <div class="multi-outdoor-list">
              <button
                v-for="outdoor in multiOutdoorOptions"
                :key="outdoor.slug"
                class="multi-outdoor-card"
                :class="{ active: selectedOutdoorSlug === outdoor.slug }"
                @click="selectMultiOutdoor(outdoor.slug)"
              >
                <div class="multi-outdoor-title">{{ outdoor.title }}</div>
                <div class="multi-outdoor-meta">
                  До {{ getOutdoorPortsMax(outdoor) || '?' }} внутренних
                  · {{ formatKw(getCoolingKw(outdoor)) }} кВт
                </div>
              </button>
            </div>
          </div>

          <div class="multi-config-column">
            <div class="control-label">2. Внутренние блоки</div>
            <div v-if="multiIndoorFilterHint" class="multi-compat-hint">
              {{ multiIndoorFilterHint }}
            </div>
            <div class="multi-indoor-list">
              <div v-for="indoor in multiIndoorOptionsFiltered" :key="indoor.slug" class="multi-indoor-item">
                <div class="multi-indoor-main">
                  <div class="multi-indoor-title">{{ indoor.title }}</div>
                  <div class="multi-indoor-meta">
                    {{ formatKw(getCoolingKw(indoor)) }} кВт
                    · {{ getSpecValue(indoor, ['indoor_type', 'Тип внутреннего блока']) || 'внутренний блок' }}
                  </div>
                </div>
                <div class="multi-qty-control">
                  <button type="button" @click="changeIndoorQty(indoor.slug, -1)">−</button>
                  <span>{{ Number(selectedIndoorQuantities[indoor.slug] || 0) }}</span>
                  <button type="button" @click="changeIndoorQty(indoor.slug, 1)">+</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="multi-config-summary" :class="{ invalid: !multiValidation.isValid }">
          <p>{{ multiValidation.summary }}</p>
          <div v-if="hasOutdoorStrictComboRestriction || hasOutdoorCapacityComboRestriction" class="multi-rules-block">
            <div class="multi-rules-label">
              {{
                hasOutdoorStrictComboRestriction
                  ? 'Допустимые строгие конфигурации:'
                  : 'Допустимые комбинации free match:'
              }}
            </div>
            <div class="multi-rules-list">
              <span
                v-for="rule in (hasOutdoorStrictComboRestriction ? selectedOutdoorComboRules : selectedOutdoorCapacityCombos)"
                :key="hasOutdoorStrictComboRestriction ? rule.signature : rule"
                class="multi-rule-pill"
                :class="{
                  active: hasOutdoorStrictComboRestriction
                    ? (matchedComboRule && matchedComboRule.signature === rule.signature)
                    : (matchedCapacityCombo && matchedCapacityCombo === rule)
                }"
              >
                {{ hasOutdoorStrictComboRestriction ? formatComboRule(rule) : rule }}
              </span>
            </div>
          </div>
          <ul v-if="multiValidation.reasons.length > 0" class="multi-config-errors">
            <li v-for="reason in multiValidation.reasons" :key="reason">{{ reason }}</li>
          </ul>
          <div class="multi-config-actions">
            <button type="button" class="filters-reset-btn" @click="clearMultiConfig">Сбросить</button>
            <a :href="multiLeadUrl" class="load-more-btn" :class="{ disabled: !multiValidation.isValid }">
              Отправить менеджеру
            </a>
          </div>
        </div>
      </template>
    </section>

    <section class="filters-toolbar">
      <button class="filters-toggle-btn" type="button" @click="advancedFiltersOpen = !advancedFiltersOpen">
        <span class="material-icons-round">tune</span>
        <span>{{ advancedFiltersOpen ? 'Скрыть фильтры' : 'Фильтры' }}</span>
      </button>
      <button
        v-if="hasActiveAdvancedFilters"
        type="button"
        class="filters-reset-btn"
        @click="resetAdvancedFilters"
      >
        Сбросить
      </button>
    </section>

    <transition name="fade-up">
      <section v-if="advancedFiltersOpen" class="glass-panel advanced-panel">
        <div class="advanced-row">
          <div class="section-head">
            <div class="control-label">Бренд</div>
            <div v-if="loadingBrands" class="label-hint">Обновляем список...</div>
          </div>
          <div class="brand-strip">
            <button
              class="brand-pill"
              :class="{ active: activeBrandSlug === null }"
              @click="toggleBrand('__all__')"
            >
              Все бренды
            </button>

            <button
              v-for="brand in availableBrands"
              :key="brand.slug"
              class="brand-pill"
              :class="{ active: activeBrandSlug === brand.slug }"
              @click="toggleBrand(brand.slug)"
            >
              <img
                v-if="getBrandLogo(brand)"
                :src="getBrandLogo(brand)"
                :alt="brand.title"
                class="brand-pill-logo"
              />
              <span>{{ brand.title }}</span>
            </button>
          </div>
        </div>

        <div class="advanced-row">
          <label class="control-label" for="catalog-sort">Сортировка</label>
          <select id="catalog-sort" v-model="sort" class="filters-select" @change="onSortChange">
            <option value="recommended">Рекомендуемые</option>
            <option value="newest">Сначала новые</option>
            <option value="price_asc">Сначала дешевле</option>
            <option value="price_desc">Сначала дороже</option>
          </select>
        </div>

        <div class="advanced-row">
          <div class="control-label">Тип компрессора</div>
          <div class="quick-chip-row">
            <button
              class="quick-chip"
              :class="{ active: currentIsInverter === true }"
              @click="toggleBooleanFilter('is_inverter', true)"
            >
              Инвертор
            </button>
            <button
              class="quick-chip"
              :class="{ active: currentIsInverter === false }"
              @click="toggleBooleanFilter('is_inverter', false)"
            >
              On/Off
            </button>
          </div>
        </div>

        <div class="advanced-row">
          <div class="control-label">Дополнительно</div>
          <div class="quick-chip-row">
            <button
              class="quick-chip"
              :class="{ active: currentHasWifi === true }"
              @click="toggleBooleanFilter('has_wifi', true)"
            >
              Wi-Fi
            </button>
            <button
              class="quick-chip"
              :class="{ active: currentHasFreshAir === true }"
              @click="toggleBooleanFilter('has_fresh_air', true)"
            >
              Приток воздуха
            </button>
          </div>
        </div>

        <div class="advanced-row">
          <div class="control-label">Обогрев</div>
          <div class="quick-chip-row">
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-15' }" @click="setHeatingMin('-15')">
              до -15°C
            </button>
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-20' }" @click="setHeatingMin('-20')">
              до -20°C
            </button>
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-25' }" @click="setHeatingMin('-25')">
              до -25°C
            </button>
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-30' }" @click="setHeatingMin('-30')">
              до -30°C
            </button>
          </div>
        </div>
      </section>
    </transition>

    <div v-if="!dynamicActive" class="catalog-static-slot">
      <slot />
    </div>

    <div v-if="!dynamicActive && hasMore" class="load-more-wrap">
      <button class="load-more-btn" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? 'Загружаем...' : 'Показать еще' }}
      </button>
    </div>

    <div v-if="dynamicActive && loadingInitial" class="grid skeleton-grid">
      <div v-for="i in 8" :key="`skeleton-${i}`" class="skeleton-card" />
    </div>

    <div v-else-if="dynamicActive && products.length > 0" class="catalog-content">
      <section v-if="showPopularModels" class="popular-section" aria-labelledby="popular-models-title">
        <div class="catalog-section-head">
          <h2 id="popular-models-title">Популярные модели</h2>
        </div>
        <transition-group name="fade-up" tag="div" class="grid popular-grid">
          <ProductCard
            v-for="product in popularModels"
            :key="`popular-${product.id}`"
            :product="product"
            :showInstallation="true"
            :refreshProductOnMount="false"
          />
        </transition-group>
      </section>

      <section class="all-products-section" aria-labelledby="all-products-title">
        <div class="catalog-section-head">
          <h2 id="all-products-title">Все модели</h2>
        </div>
        <transition-group name="fade-up" tag="div" class="grid">
          <ProductCard
            v-for="product in products"
            :key="product.id"
            :product="product"
            :showInstallation="true"
            :refreshProductOnMount="false"
          />
        </transition-group>
      </section>

      <div v-if="loadingMore" class="grid skeleton-grid skeleton-grid-more">
        <div v-for="i in 4" :key="`skeleton-more-${i}`" class="skeleton-card" />
      </div>

      <div v-if="hasMore" class="load-more-wrap">
        <button class="load-more-btn" :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? 'Загружаем...' : 'Показать еще' }}
        </button>
      </div>
    </div>

    <div v-else-if="dynamicActive" class="empty-status card">
      <span class="material-icons-round large">search_off</span>
      <h3>Товары не найдены</h3>
      <p>Попробуйте выбрать другой бренд или категорию.</p>
    </div>
  </div>
</template>

<style scoped>
.catalog-header {
  margin-bottom: 1.5rem;
}

.catalog-controls {
  margin-bottom: 1rem;
}

.controls-top {
  display: flex;
  align-items: center;
  gap: 1rem;
  justify-content: space-between;
  flex-wrap: wrap;
}

.header-top {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  margin-bottom: 1rem;
}

.breadcrumb {
  font-size: 0.9rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  min-width: 0;
}

.breadcrumb a {
  color: inherit;
  text-decoration: none;
}

.breadcrumb a:hover {
  color: var(--primary);
}

.sep {
  opacity: 0.5;
}

.catalog-desktop-only {
  display: flex !important;
}

.catalog-mobile-only {
  display: none !important;
}

.header-search {
  width: min(620px, 58vw);
  margin-left: 0;
}

.search-toggle {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  color: var(--text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.search-toggle.active {
  border-color: rgba(0, 127, 128, 0.8);
}

.mobile-search {
  width: 100%;
  margin-bottom: 0.85rem;
}

.catalog-header h1 {
  font-size: clamp(2rem, 4vw, 2.7rem);
  margin: 0 0 0.5rem;
  line-height: 1.12;
}

.header-description {
  max-width: 760px;
  color: var(--text-muted);
  margin: 0;
}

.semi-guide-link {
  display: inline-flex;
  margin-top: 0.7rem;
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--primary);
  text-decoration: none;
}

.semi-guide-link:hover {
  text-decoration: underline;
}

.glass-panel {
  background: var(--panel-glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--panel-glass-border);
  border-radius: 18px;
  box-shadow: var(--panel-glass-shadow);
  padding: 1rem;
  margin-bottom: 1rem;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.section-label {
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.label-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.brand-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  overflow: visible;
  padding-bottom: 0.25rem;
}

.brand-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  flex: 0 0 auto;
  max-width: 100%;
  min-width: 0;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  border-radius: 999px;
  padding: 0.52rem 0.95rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.brand-pill span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brand-pill:hover {
  border-color: var(--panel-chip-hover-border);
  transform: translateY(-1px);
}

.brand-pill.active {
  color: var(--panel-active-text);
  border-color: transparent;
  background: var(--panel-active-gradient-alt);
  box-shadow: 0 10px 24px -16px rgba(18, 90, 145, 0.85);
}

.brand-pill-logo {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  object-fit: contain;
  display: block;
}

.search-container {
  margin: 1rem 0 1.6rem;
  max-width: 680px;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 0.9rem;
  color: var(--text-muted);
}

.search-input {
  width: 100%;
  border: 1px solid var(--panel-input-border);
  border-radius: 14px;
  background: var(--panel-input-bg);
  color: var(--text);
  font-size: 0.96rem;
  padding: 0.8rem 1rem 0.8rem 2.85rem;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-input:focus {
  outline: none;
  border-color: rgba(0, 127, 128, 0.65);
  box-shadow: 0 0 0 4px rgba(0, 127, 128, 0.12);
}

.quick-power-panel {
  margin-top: -0.1rem;
}

.quick-chip-row {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.quick-chip {
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-chip-bg);
  color: var(--text);
  border-radius: 999px;
  padding: 0.48rem 0.9rem;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.2s ease, background 0.2s ease;
}

.quick-chip:hover {
  transform: translateY(-1px);
  border-color: var(--panel-chip-hover-border);
}

.quick-chip.active {
  color: var(--panel-active-text);
  border-color: transparent;
  background: var(--panel-active-gradient-alt);
}

.multi-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.multi-config-column {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.multi-config-empty {
  font-size: 0.92rem;
  color: var(--text-muted);
}

.multi-compat-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}
.multi-outdoor-list,
.multi-indoor-list {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.multi-outdoor-card {
  width: 100%;
  text-align: left;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-chip-bg);
  border-radius: 12px;
  padding: 0.72rem 0.82rem;
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.multi-outdoor-card:hover {
  border-color: var(--panel-chip-hover-border);
  transform: translateY(-1px);
}

.multi-outdoor-card.active {
  border-color: transparent;
  background: var(--panel-active-gradient);
  color: var(--panel-active-text);
}

.multi-outdoor-title,
.multi-indoor-title {
  font-size: 0.9rem;
  font-weight: 700;
}

.multi-outdoor-meta,
.multi-indoor-meta {
  margin-top: 0.25rem;
  font-size: 0.82rem;
  opacity: 0.86;
}

.multi-indoor-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-chip-bg);
  border-radius: 12px;
  padding: 0.62rem 0.75rem;
}

.multi-indoor-main {
  min-width: 0;
}

.multi-qty-control {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.multi-qty-control button {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  color: var(--text);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.multi-qty-control span {
  min-width: 20px;
  text-align: center;
  font-weight: 700;
}

.multi-config-summary {
  margin-top: 0.85rem;
  border: 1px solid var(--panel-chip-border);
  border-radius: 12px;
  padding: 0.78rem 0.85rem;
  background: var(--panel-chip-bg);
}

.multi-config-summary.invalid {
  border-color: var(--error);
}

.multi-config-summary p {
  margin: 0;
  font-size: 0.9rem;
}

.multi-rules-block {
  margin-top: 0.55rem;
}

.multi-rules-label {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-bottom: 0.35rem;
}

.multi-rules-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.multi-rule-pill {
  border-radius: 999px;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  padding: 0.28rem 0.62rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--text);
}

.multi-rule-pill.active {
  border-color: transparent;
  color: var(--panel-active-text);
  background: var(--panel-active-gradient-alt);
}

.multi-config-errors {
  margin: 0.55rem 0 0;
  padding-left: 1.1rem;
  color: var(--error-text);
  font-size: 0.84rem;
}

.multi-config-actions {
  margin-top: 0.7rem;
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.multi-config-actions .load-more-btn {
  text-decoration: none;
}

.multi-config-actions .load-more-btn.disabled {
  pointer-events: none;
  opacity: 0.65;
}

.filters-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0.3rem 0 1rem;
}

.filters-toggle-btn,
.filters-reset-btn {
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  color: var(--text);
  border-radius: 999px;
  padding: 0.52rem 0.92rem;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.filters-reset-btn {
  color: var(--text-muted);
}

.advanced-panel {
  margin-top: -0.2rem;
}

.advanced-row {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.advanced-row + .advanced-row {
  margin-top: 0.9rem;
}

.control-label {
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  text-transform: uppercase;
}

.filters-select {
  width: 100%;
  max-width: 280px;
  border: 1px solid var(--panel-input-border);
  border-radius: 12px;
  background: var(--panel-input-bg);
  color: var(--text);
  font-size: 0.9rem;
  padding: 0.6rem 0.7rem;
}

.catalog-content {
  display: flex;
  flex-direction: column;
  gap: 1.4rem;
}

.popular-section,
.all-products-section {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.catalog-section-head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}

.catalog-section-head h2,
.catalog-seo-block h2 {
  margin: 0;
  color: var(--text);
  font-size: 1.35rem;
  line-height: 1.2;
}

.popular-grid {
  padding-bottom: 0.15rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.3rem;
}

.skeleton-grid {
  margin-top: 0.2rem;
}

.skeleton-grid-more {
  margin-top: 0.8rem;
}

.skeleton-card {
  border-radius: 14px;
  min-height: 390px;
  background: var(--panel-skeleton);
  background-size: 220% 100%;
  animation: shimmer 1.25s infinite linear;
}

@keyframes shimmer {
  to {
    background-position-x: -220%;
  }
}

.load-more-wrap {
  display: flex;
  justify-content: center;
  margin-top: 0.4rem;
}

.load-more-btn {
  border: none;
  border-radius: 999px;
  padding: 0.82rem 1.5rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--panel-active-text);
  background: var(--panel-active-gradient);
  box-shadow: 0 14px 28px -20px rgba(17, 122, 142, 1);
  cursor: pointer;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.load-more-btn:hover {
  transform: translateY(-1px);
}

.load-more-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.fade-up-enter-active,
.fade-up-leave-active {
  transition: all 0.26s ease;
}

.fade-up-enter-from,
.fade-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.empty-status {
  text-align: center;
  padding: 4rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.large {
  font-size: 4rem;
  color: var(--text-muted);
  opacity: 0.55;
}

.catalog-seo-block {
  margin-top: 2.2rem;
  padding-top: 1.6rem;
  border-top: 1px solid var(--panel-glass-border);
  color: var(--text-muted);
}

.catalog-seo-block p {
  max-width: 880px;
  margin: 0.75rem 0 0;
  line-height: 1.7;
}

@media (max-width: 980px) {
  .multi-config-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .controls-top {
    align-items: stretch;
  }

  .header-top {
    align-items: center;
    margin-bottom: 0.8rem;
  }

  .catalog-desktop-only {
    display: none !important;
  }

  .catalog-mobile-only {
    display: flex !important;
  }

  .header-search {
    width: 100%;
  }

  .breadcrumb {
    font-size: 0.85rem;
    gap: 0.4rem;
    margin-right: auto;
  }

  .glass-panel {
    border-radius: 16px;
    padding: 0.9rem;
  }

  .brand-pill {
    padding: 0.5rem 0.84rem;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  .filters-toolbar {
    margin-top: 0;
  }
}
</style>
