<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { api, type Product, type ManagerBrand } from '../api';
import { X, Save, Plus, Trash2, Edit3, Globe, Hash, Tag } from 'lucide-vue-next';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';
import SpecKeyCombobox from './SpecKeyCombobox.vue';
import { specsTranslations } from '../utils/specsTranslations';

interface TagItem {
    id: number;
    title: string;
    slug: string;
}

interface TagGroupItem {
    id: number;
    title: string;
    slug: string;
    color: string;
    allow_multiple: boolean;
    tags: TagItem[];
}

interface MultiComboRuleLine {
    slug: string;
    qty: number;
}

interface MultiComboRule {
    id: string;
    title: string;
    lines: MultiComboRuleLine[];
}

type MultiCompatMode = 'free_match' | 'strict';

const props = defineProps<{
    modelValue: boolean;
    product: Product | null;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const form = ref<any>({
    title: '',
    slug: '',
    price: 0,
    old_price: 0,
    is_published: true,
});

const specs = ref<{ key: string; value: string }[]>([]);
const selectedTagIds = ref<Set<number>>(new Set());
const loading = ref(false);
const formMessage = ref('');
const formServerErrors = ref<Record<string, string>>({});
const knownKeys = ref<string[]>([]);
const tagGroups = ref<TagGroupItem[]>([]);
const tagsLoading = ref(false);
const brandsLoading = ref(false);
const tagSearchQuery = ref('');
const managerBrands = ref<ManagerBrand[]>([]);
const selectedBrandEntityId = ref<number | null>(null);
const vitebskQty = ref(0);
const supplierOffers = ref<any[]>([]);
const localStockSaving = ref(false);
const unlinkingMappingId = ref<number | null>(null);
const COMPATIBLE_INDOOR_KEY = 'compatible_indoor_slugs';
const COMPATIBLE_OUTDOOR_KEY = 'compatible_outdoor_slugs';
const MULTI_COMBO_RULES_KEY = 'multi_combo_rules';
const MULTI_COMPAT_MODE_KEY = 'multi_compat_mode';
const MULTI_CAPACITY_COMBOS_KEY = 'multi_capacity_combos';
const COMPATIBILITY_KEYS = new Set([
    COMPATIBLE_INDOOR_KEY,
    COMPATIBLE_OUTDOOR_KEY,
    MULTI_COMBO_RULES_KEY,
    MULTI_COMPAT_MODE_KEY,
    MULTI_CAPACITY_COMBOS_KEY,
]);
const compatibilityIndoorSlugs = ref<string[]>([]);
const compatibilityOutdoorSlugs = ref<string[]>([]);
const multiComboRules = ref<MultiComboRule[]>([]);
const multiCompatMode = ref<MultiCompatMode>('free_match');
const capacityCombosInput = ref('');
const compatibilityQuery = ref('');
const compatibilityResults = ref<Product[]>([]);
const compatibilityLoading = ref(false);
const compatibilityInfo = ref('');
const creatingBrand = ref(false);
const newBrandTitle = ref('');

const normalizeText = (value: unknown): string => String(value ?? '').toLowerCase().replace(/ё/g, 'е').trim();
const normalizeBrandToken = (value: unknown): string => normalizeText(value).replace(/[^a-z0-9а-я]/g, '');
const INVALID_BRAND_TOKENS = new Set([
    'мультисплитсистема',
    'сплитсистема',
    'внутреннийблок',
    'наружныйблок',
    'полупромышленныйкондиционер',
    'кондиционер',
]);

const isInvalidBrandToken = (token: string): boolean => INVALID_BRAND_TOKENS.has(token);

const parseSlugList = (value: unknown): string[] => {
    if (Array.isArray(value)) {
        return Array.from(
            new Set(
                value
                    .map((item) => String(item ?? '').trim())
                    .filter(Boolean),
            ),
        );
    }
    if (typeof value === 'string') {
        return Array.from(
            new Set(
                value
                    .split(/[,\n;]/g)
                    .map((item) => item.trim())
                    .filter(Boolean),
            ),
        );
    }
    return [];
};

const normalizeCapacityToken = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '';
    const numeric = raw.replace(',', '.').match(/\d+(?:\.\d+)?/);
    if (!numeric) return '';
    const parsed = Number.parseFloat(numeric[0]);
    if (!Number.isFinite(parsed) || parsed <= 0) return '';

    let klass = parsed;
    if (klass >= 1000) klass = klass / 1000;
    const rounded = Math.max(1, Math.round(klass));
    return String(rounded).padStart(2, '0');
};

const normalizeCapacityCombo = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '';
    const tokens = raw
        .split('+')
        .map((item) => normalizeCapacityToken(item))
        .filter(Boolean);
    if (tokens.length === 0) return '';
    return tokens
        .sort((a, b) => Number(a) - Number(b))
        .join('+');
};

const parseCapacityCombos = (value: unknown): string[] => {
    const chunks = Array.isArray(value)
        ? value.map((item) => String(item ?? ''))
        : String(value ?? '')
            .split(/[,\n;]/g)
            .map((item) => item.trim());
    const unique = new Set<string>();
    for (const chunk of chunks) {
        const normalized = normalizeCapacityCombo(chunk);
        if (!normalized) continue;
        unique.add(normalized);
    }
    return Array.from(unique);
};

const normalizedCapacityCombos = computed(() => parseCapacityCombos(capacityCombosInput.value));

const makeRuleId = (): string => `rule-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const toPositiveInt = (value: unknown): number => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 1;
    return Math.max(1, Math.floor(parsed));
};

const buildEmptyComboRule = (): MultiComboRule => ({
    id: makeRuleId(),
    title: '',
    lines: [{ slug: '', qty: 1 }],
});

const normalizeRuleLine = (line: unknown): MultiComboRuleLine | null => {
    if (!line) return null;
    if (typeof line === 'string') {
        const [rawSlug, rawQty] = line.split(':');
        const slug = String(rawSlug || '').trim();
        if (!slug) return null;
        return {
            slug,
            qty: toPositiveInt(rawQty || 1),
        };
    }
    if (typeof line !== 'object') return null;

    const obj = line as Record<string, unknown>;
    const slug = String(obj.slug ?? obj.indoor_slug ?? obj.model_slug ?? '').trim();
    if (!slug) return null;
    return {
        slug,
        qty: toPositiveInt(obj.qty ?? obj.quantity ?? obj.count ?? 1),
    };
};

const normalizeRuleLines = (lines: unknown): MultiComboRuleLine[] => {
    if (!Array.isArray(lines)) return [];
    const acc = new Map<string, number>();
    for (const line of lines) {
        const normalized = normalizeRuleLine(line);
        if (!normalized) continue;
        const prev = Number(acc.get(normalized.slug) || 0);
        acc.set(normalized.slug, prev + normalized.qty);
    }
    return Array.from(acc.entries()).map(([slug, qty]) => ({ slug, qty }));
};

const parseMultiComboRules = (value: unknown): MultiComboRule[] => {
    if (!Array.isArray(value)) return [];
    return value
        .map((item) => {
            if (!item || typeof item !== 'object') return null;
            const obj = item as Record<string, unknown>;
            const rawLines = obj.lines ?? obj.items ?? [];
            const lines = normalizeRuleLines(rawLines);
            if (lines.length === 0) return null;
            return {
                id: makeRuleId(),
                title: String(obj.title ?? obj.name ?? '').trim(),
                lines,
            } as MultiComboRule;
        })
        .filter((rule): rule is MultiComboRule => Boolean(rule));
};

const serializeMultiComboRules = (): Array<{ title?: string; lines: MultiComboRuleLine[] }> => (
    multiComboRules.value
        .map((rule) => {
            const lines = normalizeRuleLines(rule.lines);
            if (lines.length === 0) return null;
            const title = String(rule.title || '').trim();
            if (!title) return { lines };
            return { title, lines };
        })
        .filter((rule): rule is { title?: string; lines: MultiComboRuleLine[] } => Boolean(rule))
);

const getProductSpecsMap = (product: Product | null | undefined): Record<string, any> => (
    ((product as any)?.specs || {}) as Record<string, any>
);

const getBrandFromSpecs = (product: Product | null | undefined): string => {
    const specsMap = getProductSpecsMap(product);
    const raw = specsMap.brand ?? specsMap['Бренд'] ?? specsMap['Марка'] ?? specsMap['Производитель'];
    return String(raw ?? '').trim();
};

const getBrandFromTags = (product: Product | null | undefined): string => {
    const tags = ((product as any)?.tags || []) as Array<any>;
    const brandTag = tags.find((tag) => {
        const groupSlug = normalizeText(tag?.group?.slug || tag?.group_slug || '');
        const groupTitle = normalizeText(tag?.group_title || tag?.group?.title || '');
        return groupSlug === 'brand' || groupTitle === 'бренд' || groupTitle === 'brand';
    });
    return String(brandTag?.title ?? '').trim();
};

const getResolvedBrandName = (product: Product | null | undefined): string => {
    const candidates = [getBrandFromTags(product), getBrandFromSpecs(product)]
        .map((value) => String(value || '').trim())
        .filter(Boolean);
    if (candidates.length === 0) return '';
    const valid = candidates.find((value) => !isInvalidBrandToken(normalizeBrandToken(value)));
    return valid ?? candidates[0] ?? '';
};

const getResolvedBrandToken = (product: Product | null | undefined): string => {
    const token = normalizeBrandToken(getResolvedBrandName(product));
    if (!token || isInvalidBrandToken(token)) return '';
    return token;
};

const getCurrentEditedBrandFromSpecs = (): string => {
    const byKey = new Map(
        specs.value.map((row) => [normalizeText(row.key), String(row.value ?? '').trim()]),
    );
    return (
        byKey.get('brand')
        || byKey.get('бренд')
        || byKey.get('марка')
        || byKey.get('производитель')
        || ''
    ).trim();
};

const isIndoorProduct = (product: Product): boolean => {
    const specsMap = getProductSpecsMap(product);
    const typeText = normalizeText(specsMap.type ?? specsMap['Тип']);
    const titleText = normalizeText((product as any)?.title);
    return typeText.includes('внутрен') || titleText.includes('внутренний блок');
};

const isOutdoorProduct = (product: Product): boolean => {
    if (isIndoorProduct(product)) return false;
    const specsMap = getProductSpecsMap(product);
    const typeText = normalizeText(specsMap.type ?? specsMap['Тип']);
    const titleText = normalizeText((product as any)?.title);
    return typeText.includes('наруж') || typeText.includes('мульти') || titleText.includes('мульти-сплит');
};

const isMultiRelatedProduct = (product: Product): boolean => {
    const tags = (product as any).tags || [];
    return tags.some((tag: any) => tag.slug === 'cat-multi');
};

const categoryGroup = computed(() => tagGroups.value.find((group) => group.slug === 'category') || null);
const brandGroup = computed(() => tagGroups.value.find((group) => group.slug === 'brand') || null);
const brandOptions = computed(() => [...managerBrands.value].sort((a, b) => {
    const orderDiff = Number(a.sort_order || 0) - Number(b.sort_order || 0);
    if (orderDiff !== 0) return orderDiff;
    return String(a.title || '').localeCompare(String(b.title || ''), 'ru');
}));
const brandTagsSorted = computed(() => {
    const group = brandGroup.value;
    if (!group) return [];
    return [...group.tags].sort((a, b) => String(a.title || '').localeCompare(String(b.title || ''), 'ru'));
});
const selectedBrandTag = computed(() => {
    const group = brandGroup.value;
    if (!group) return null;
    return group.tags.find((tag) => selectedTagIds.value.has(tag.id)) || null;
});
const selectedBrandTagId = computed<number | null>(() => selectedBrandTag.value?.id ?? null);
const selectedBrandEntity = computed<ManagerBrand | null>(() => {
    if (!selectedBrandEntityId.value) return null;
    return managerBrands.value.find((brand) => brand.id === selectedBrandEntityId.value) || null;
});
const currentBrandId = computed<number | null>(() => {
    const selected = Number(selectedBrandEntityId.value || 0);
    if (Number.isFinite(selected) && selected > 0) return selected;
    const raw = Number((props.product as any)?.brand_id || 0);
    return Number.isFinite(raw) && raw > 0 ? raw : null;
});
const currentBrandTitle = computed<string>(() => {
    const candidates = [
        String(selectedBrandEntity.value?.title || '').trim(),
        String(selectedBrandTag.value?.title || '').trim(),
        String(getCurrentEditedBrandFromSpecs() || '').trim(),
        String(getResolvedBrandName(props.product) || '').trim(),
    ].filter(Boolean);
    if (candidates.length === 0) return '';
    const valid = candidates.find((value) => !isInvalidBrandToken(normalizeBrandToken(value)));
    return valid ?? candidates[0] ?? '';
});
const currentBrandToken = computed<string>(() => {
    const token = normalizeBrandToken(currentBrandTitle.value);
    if (!token || isInvalidBrandToken(token)) return '';
    return token;
});
const hasBrandContext = computed(() => Boolean(currentBrandToken.value || currentBrandId.value || currentBrandTitle.value));

const isSameBrandCandidate = (candidate: Product): boolean => {
    if (currentBrandToken.value) {
        const candidateToken = getResolvedBrandToken(candidate);
        if (candidateToken) return candidateToken === currentBrandToken.value;
        return false;
    }

    const candidateBrandIdRaw = Number((candidate as any)?.brand_id || 0);
    const candidateBrandId = Number.isFinite(candidateBrandIdRaw) && candidateBrandIdRaw > 0
        ? candidateBrandIdRaw
        : null;
    if (currentBrandId.value && candidateBrandId) return candidateBrandId === currentBrandId.value;

    if (hasBrandContext.value) return false;
    return true;
};

const filterCompatibilityCandidates = (items: Product[]): Product[] => (
    items.filter((item) => {
        if (!isMultiRelatedProduct(item)) return false;
        if (item.id === props.product?.id) return false;
        if (!isSameBrandCandidate(item)) return false;
        return true;
    })
);

const indoorSlugOptions = computed(() => {
    const all = new Set<string>();
    for (const slug of compatibilityIndoorSlugs.value) {
        const clean = String(slug || '').trim();
        if (clean) all.add(clean);
    }
    for (const item of compatibilityResults.value) {
        const slug = String((item as any)?.slug || '').trim();
        if (!slug) continue;
        if (isIndoorProduct(item)) all.add(slug);
    }
    for (const rule of multiComboRules.value) {
        for (const line of rule.lines) {
            const clean = String(line.slug || '').trim();
            if (clean) all.add(clean);
        }
    }
    return Array.from(all).sort((a, b) => a.localeCompare(b, 'ru'));
});

const addMultiComboRule = () => {
    multiComboRules.value = [...multiComboRules.value, buildEmptyComboRule()];
};

const removeMultiComboRule = (ruleId: string) => {
    multiComboRules.value = multiComboRules.value.filter((rule) => rule.id !== ruleId);
};

const addMultiComboRuleLine = (ruleId: string) => {
    const rule = multiComboRules.value.find((item) => item.id === ruleId);
    if (!rule) return;
    rule.lines.push({ slug: '', qty: 1 });
};

const removeMultiComboRuleLine = (ruleId: string, lineIndex: number) => {
    const rule = multiComboRules.value.find((item) => item.id === ruleId);
    if (!rule) return;
    if (rule.lines.length <= 1) {
        rule.lines[0] = { slug: '', qty: 1 };
        return;
    }
    rule.lines.splice(lineIndex, 1);
};

const fillRuleFromIndoorCompatibility = (ruleId: string) => {
    const rule = multiComboRules.value.find((item) => item.id === ruleId);
    if (!rule) return;
    if (compatibilityIndoorSlugs.value.length === 0) return;
    rule.lines = compatibilityIndoorSlugs.value.map((slug) => ({ slug, qty: 1 }));
};

const getRulePreview = (rule: MultiComboRule): string => {
    const parts = normalizeRuleLines(rule.lines).map((line) => `${line.qty}×${line.slug}`);
    return parts.join(' + ');
};

const upsertSpecRow = (key: string, value: string) => {
    const existing = specs.value.find((row) => row.key === key);
    if (existing) {
        existing.value = value;
    } else {
        specs.value.unshift({ key, value });
    }
};

const removeSpecRowsByNormalizedKeys = (normalizedKeys: string[]) => {
    const keySet = new Set(normalizedKeys.map((k) => normalizeText(k)));
    specs.value = specs.value.filter((row) => !keySet.has(normalizeText(row.key)));
};

const setBrandTag = (tagId: number | null) => {
    const group = brandGroup.value;
    if (!group) return;

    for (const tag of group.tags) {
        selectedTagIds.value.delete(tag.id);
    }

    if (!tagId) {
        removeSpecRowsByNormalizedKeys(['brand', 'бренд', 'марка', 'производитель']);
        selectedBrandEntityId.value = null;
        return;
    }

    const selected = group.tags.find((tag) => tag.id === tagId) || null;
    if (!selected) return;
    selectedTagIds.value.add(selected.id);
    upsertSpecRow('brand', selected.title);

    const bySlug = managerBrands.value.find((brand) => normalizeText(brand.slug) === normalizeText(selected.slug));
    const byTitle = managerBrands.value.find((brand) => normalizeText(brand.title) === normalizeText(selected.title));
    selectedBrandEntityId.value = bySlug?.id ?? byTitle?.id ?? null;
};

const applyBrandEntitySelection = (nextId: number | null) => {
    selectedBrandEntityId.value = nextId;

    if (!nextId) {
        setBrandTag(null);
        return;
    }

    const brand = managerBrands.value.find((item) => item.id === nextId);
    if (!brand) return;
    upsertSpecRow('brand', brand.title);

    const group = brandGroup.value;
    if (!group) return;

    const tagBySlug = group.tags.find((tag) => normalizeText(tag.slug) === normalizeText(brand.slug));
    const tagByTitle = group.tags.find((tag) => normalizeText(tag.title) === normalizeText(brand.title));
    const targetTag = tagBySlug || tagByTitle;
    if (targetTag) setBrandTag(targetTag.id);
};

const onBrandEntitySelectChange = (event: Event) => {
    const target = event.target as HTMLSelectElement | null;
    const raw = Number(target?.value || 0);
    applyBrandEntitySelection(Number.isFinite(raw) && raw > 0 ? raw : null);
};

const createAndSelectBrand = async () => {
    const title = String(newBrandTitle.value || '').trim();
    if (!title) {
        formMessage.value = 'Введите название бренда.';
        return;
    }

    creatingBrand.value = true;
    formMessage.value = '';
    try {
        await fetchBrands();
        const existing = managerBrands.value.find((brand) => normalizeText(brand.title) === normalizeText(title));
        if (existing) {
            await fetchTags();
            applyBrandEntitySelection(existing.id);
            newBrandTitle.value = '';
            return;
        }

        const created = await api.createManagerBrand({
            title,
        });
        await fetchBrands(true);
        await fetchTags(true);
        applyBrandEntitySelection(created.id);
        newBrandTitle.value = '';
        formMessage.value = '';
    } catch (e) {
        formMessage.value = `Не удалось создать бренд: ${getApiErrorMessage(e)}`;
    } finally {
        creatingBrand.value = false;
    }
};

const onBrandSelectChange = (event: Event) => {
    const target = event.target as HTMLSelectElement | null;
    const raw = Number(target?.value || 0);
    setBrandTag(Number.isFinite(raw) && raw > 0 ? raw : null);
};

const setCategoryTag = async (categorySlug: string) => {
    if (!categorySlug) return;
    if (tagGroups.value.length === 0) await fetchTags();
    const group = categoryGroup.value;
    if (!group) return;
    for (const tag of group.tags) {
        selectedTagIds.value.delete(tag.id);
    }
    const target = group.tags.find((tag) => tag.slug === categorySlug);
    if (target) selectedTagIds.value.add(target.id);
};

const applyPreset = async (preset: 'multi_outdoor' | 'multi_indoor' | 'semi_cassette' | 'semi_duct' | 'semi_floor_ceiling' | 'semi_column') => {
    if (preset === 'multi_outdoor') {
        await setCategoryTag('cat-multi');
        upsertSpecRow('type', 'мульти-сплит-система');
        return;
    }
    if (preset === 'multi_indoor') {
        await setCategoryTag('cat-multi');
        upsertSpecRow('type', 'внутренний блок');
        return;
    }

    await setCategoryTag('cat-industrial');
    upsertSpecRow('type', 'полупромышленный кондиционер');
    if (preset === 'semi_cassette') upsertSpecRow('indoor_type', 'кассетный');
    if (preset === 'semi_duct') upsertSpecRow('indoor_type', 'канальный');
    if (preset === 'semi_floor_ceiling') upsertSpecRow('indoor_type', 'напольно-потолочный');
    if (preset === 'semi_column') upsertSpecRow('indoor_type', 'колонный');
};

const addCompatibilitySlug = (target: 'indoor' | 'outdoor', slug: string) => {
    const clean = slug.trim();
    if (!clean) return;
    if (target === 'indoor') {
        compatibilityIndoorSlugs.value = Array.from(new Set([...compatibilityIndoorSlugs.value, clean]));
    } else {
        compatibilityOutdoorSlugs.value = Array.from(new Set([...compatibilityOutdoorSlugs.value, clean]));
    }
};

const removeCompatibilitySlug = (target: 'indoor' | 'outdoor', slug: string) => {
    if (target === 'indoor') {
        compatibilityIndoorSlugs.value = compatibilityIndoorSlugs.value.filter((item) => item !== slug);
    } else {
        compatibilityOutdoorSlugs.value = compatibilityOutdoorSlugs.value.filter((item) => item !== slug);
    }
};

const searchCompatibilityProducts = async () => {
    const q = compatibilityQuery.value.trim();
    if (q.length < 2) {
        compatibilityResults.value = [];
        compatibilityInfo.value = '';
        return;
    }

    compatibilityLoading.value = true;
    try {
        const result = await api.smartSearchProducts(q, 40);
        compatibilityResults.value = filterCompatibilityCandidates(result);
        if (hasBrandContext.value) {
            compatibilityInfo.value = compatibilityResults.value.length > 0
                ? 'Показаны кандидаты только текущего бренда.'
                : 'Совместимые кандидаты текущего бренда не найдены.';
        } else {
            compatibilityInfo.value = 'Бренд у текущего товара не определен. Показаны все мульти-кандидаты.';
        }
    } catch (e) {
        console.error(e);
        compatibilityResults.value = [];
        compatibilityInfo.value = '';
    } finally {
        compatibilityLoading.value = false;
    }
};

const guessSearchSeedForBrand = (): string => {
    const fromQuery = compatibilityQuery.value.trim();
    if (fromQuery.length >= 2) return fromQuery;
    const fromBrand = currentBrandTitle.value.trim();
    if (fromBrand.length >= 2) return fromBrand;
    const firstWord = String(form.value.title || props.product?.title || '').trim().split(/\s+/)[0] || '';
    return firstWord.length >= 2 ? firstWord : '';
};

const autoFillCompatibilityByBrand = async () => {
    compatibilityInfo.value = '';
    if (!hasBrandContext.value) {
        compatibilityInfo.value = 'Сначала задайте бренд (тег группы Бренд или spec brand).';
        return;
    }

    const seed = guessSearchSeedForBrand();
    if (!seed) {
        compatibilityInfo.value = 'Не удалось определить поисковую фразу для автоподбора.';
        return;
    }

    compatibilityLoading.value = true;
    try {
        const result = await api.smartSearchProducts(seed, 100);
        const filtered = filterCompatibilityCandidates(result);
        compatibilityResults.value = filtered;

        const beforeIndoor = compatibilityIndoorSlugs.value.length;
        const beforeOutdoor = compatibilityOutdoorSlugs.value.length;

        const indoorCandidates = filtered
            .filter((item) => isIndoorProduct(item))
            .map((item) => String(item.slug || '').trim())
            .filter(Boolean);
        const outdoorCandidates = filtered
            .filter((item) => isOutdoorProduct(item))
            .map((item) => String(item.slug || '').trim())
            .filter(Boolean);

        if (currentProductRole.value === 'outdoor') {
            compatibilityIndoorSlugs.value = Array.from(new Set([...compatibilityIndoorSlugs.value, ...indoorCandidates]));
        } else if (currentProductRole.value === 'indoor') {
            compatibilityOutdoorSlugs.value = Array.from(new Set([...compatibilityOutdoorSlugs.value, ...outdoorCandidates]));
        } else {
            compatibilityIndoorSlugs.value = Array.from(new Set([...compatibilityIndoorSlugs.value, ...indoorCandidates]));
            compatibilityOutdoorSlugs.value = Array.from(new Set([...compatibilityOutdoorSlugs.value, ...outdoorCandidates]));
        }

        const addedIndoor = compatibilityIndoorSlugs.value.length - beforeIndoor;
        const addedOutdoor = compatibilityOutdoorSlugs.value.length - beforeOutdoor;
        compatibilityInfo.value = `Автоподбор по бренду: +${Math.max(0, addedIndoor)} внутренних, +${Math.max(0, addedOutdoor)} наружных.`;
    } catch (e) {
        console.error(e);
        compatibilityInfo.value = 'Ошибка автоподбора. Проверьте сеть/API и повторите.';
    } finally {
        compatibilityLoading.value = false;
    }
};

const fetchKeys = async () => {
    try {
        const res = await api.getPublicSpecKeys();
        const combined = new Set([...Object.keys(specsTranslations), ...res.keys]);
        knownKeys.value = Array.from(combined);
    } catch (e) { console.error(e); }
};

const fetchTags = async (force = false) => {
    if (!force && tagGroups.value.length > 0) return;
    tagsLoading.value = true;
    try {
        tagGroups.value = await api.getAllTags();
    } catch (e) { console.error(e); }
    finally { tagsLoading.value = false; }
};

const fetchBrands = async (force = false) => {
    if (!force && managerBrands.value.length > 0) return;
    brandsLoading.value = true;
    try {
        const response = await api.listManagerBrands();
        managerBrands.value = response.items || [];
    } catch (e) {
        console.error(e);
        managerBrands.value = [];
    } finally {
        brandsLoading.value = false;
    }
};

const filteredTagGroups = computed(() => {
    if (!tagSearchQuery.value.trim()) return tagGroups.value;
    const q = tagSearchQuery.value.toLowerCase().trim();
    return tagGroups.value
        .map(g => ({
            ...g,
            tags: g.tags.filter(t => t.title.toLowerCase().includes(q)),
        }))
        .filter(g => g.tags.length > 0);
});

const isTagSelected = (id: number) => selectedTagIds.value.has(id);

const toggleTag = (tagId: number, group: TagGroupItem) => {
    if (selectedTagIds.value.has(tagId)) {
        selectedTagIds.value.delete(tagId);
    } else {
        if (!group.allow_multiple) {
            for (const groupTag of group.tags) {
                selectedTagIds.value.delete(groupTag.id);
            }
        }
        selectedTagIds.value.add(tagId);
    }
};

const colorMap: Record<string, string> = {
    primary: 'bg-blue-100 text-blue-800 border-blue-200',
    success: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    info: 'bg-cyan-100 text-cyan-800 border-cyan-200',
    warning: 'bg-amber-100 text-amber-800 border-amber-200',
    danger: 'bg-red-100 text-red-800 border-red-200',
    secondary: 'bg-gray-100 text-gray-700 border-gray-200',
};

const getColorClasses = (color: string) => colorMap[color] || colorMap.secondary;
const selectedColorClasses: Record<string, string> = {
    primary: 'bg-blue-600 text-white border-blue-600',
    success: 'bg-emerald-600 text-white border-emerald-600',
    info: 'bg-cyan-600 text-white border-cyan-600',
    warning: 'bg-amber-600 text-white border-amber-600',
    danger: 'bg-red-600 text-white border-red-600',
    secondary: 'bg-gray-600 text-white border-gray-600',
};
const getSelectedColorClasses = (color: string) => selectedColorClasses[color] || selectedColorClasses.secondary;

const currentProductRole = computed<'indoor' | 'outdoor' | 'unknown'>(() => {
    const specsMap: Record<string, any> = {};
    for (const row of specs.value) {
        if (row.key?.trim()) specsMap[row.key.trim()] = row.value;
    }
    const typeText = normalizeText(specsMap.type ?? specsMap['Тип']);
    const titleText = normalizeText(form.value.title || props.product?.title || '');
    const joined = `${typeText} ${titleText}`;
    if (joined.includes('внутрен')) return 'indoor';
    if (joined.includes('наруж') || joined.includes('мульти-сплит')) return 'outdoor';
    return 'unknown';
});

const isCurrentProductMulti = computed<boolean>(() => {
    const category = categoryGroup.value;
    if (category) {
        const selectedMultiTag = category.tags.find((tag) => normalizeText(tag.slug) === 'cat-multi');
        if (selectedMultiTag && selectedTagIds.value.has(selectedMultiTag.id)) return true;
    }

    const productTags = ((props.product as any)?.tags || []) as Array<{ slug?: string }>;
    if (productTags.some((tag) => normalizeText(tag?.slug || '') === 'cat-multi')) return true;

    const specsMap: Record<string, any> = {};
    for (const row of specs.value) {
        if (row.key?.trim()) specsMap[row.key.trim()] = row.value;
    }
    const typeText = normalizeText(specsMap.type ?? specsMap['Тип']);
    const titleText = normalizeText(form.value.title || props.product?.title || '');
    return (
        typeText.includes('мульти')
        || titleText.includes('мульти-сплит')
        || titleText.includes('мульти сплит')
    );
});

watch(() => props.modelValue, async (val) => {
    if (val && props.product) {
        formMessage.value = '';
        formServerErrors.value = {};
        form.value = {
            title: props.product.title,
            slug: props.product.slug,
            price: props.product.price,
            old_price: props.product.old_price,
            is_published: props.product.is_published,
        };
        
        // Convert specs object to array
        const s = props.product.specs || {};
        compatibilityIndoorSlugs.value = parseSlugList((s as any)[COMPATIBLE_INDOOR_KEY]);
        compatibilityOutdoorSlugs.value = parseSlugList((s as any)[COMPATIBLE_OUTDOOR_KEY]);
        multiComboRules.value = parseMultiComboRules((s as any)[MULTI_COMBO_RULES_KEY]);
        multiCompatMode.value = String((s as any)[MULTI_COMPAT_MODE_KEY] || 'free_match') === 'strict'
            ? 'strict'
            : 'free_match';
        capacityCombosInput.value = parseCapacityCombos((s as any)[MULTI_CAPACITY_COMBOS_KEY]).join(', ');
        specs.value = Object.entries(s)
        .filter(([key]) => !COMPATIBILITY_KEYS.has(key))
        .map(([key, value]) => {
            let sVal = String(value);
            const config = specsTranslations[key];
            if (config?.type === 'number' && config.unit) {
                // remove unit, handle case and spaces
                sVal = sVal.replace(new RegExp(config.unit + '$', 'i'), '').trim();
                const match = sVal.match(/^-?\d*[.,]?\d*/);
                sVal = match && match[0] ? match[0].replace(',', '.') : '';
            }
            return { key, value: sVal };
        });
        compatibilityQuery.value = '';
        compatibilityResults.value = [];
        compatibilityInfo.value = '';
        
        // Load tags
        const productTags = (props.product as any).tags || [];
        selectedTagIds.value = new Set(productTags.map((t: any) => t.id));
        tagSearchQuery.value = '';
        selectedBrandEntityId.value = null;
        
        if (knownKeys.value.length === 0) fetchKeys();
        await Promise.all([fetchTags(), fetchBrands()]);

        const explicitBrandId = Number((props.product as any)?.brand_id || 0);
        if (Number.isFinite(explicitBrandId) && explicitBrandId > 0) {
            selectedBrandEntityId.value = explicitBrandId;
        } else {
            const byTag = selectedBrandTag.value;
            if (byTag) {
                const matched = managerBrands.value.find((brand) => (
                    normalizeText(brand.slug) === normalizeText(byTag.slug)
                    || normalizeText(brand.title) === normalizeText(byTag.title)
                ));
                selectedBrandEntityId.value = matched?.id ?? null;
            } else {
                const bySpec = getCurrentEditedBrandFromSpecs();
                if (bySpec) {
                    const matched = managerBrands.value.find((brand) => normalizeText(brand.title) === normalizeText(bySpec));
                    selectedBrandEntityId.value = matched?.id ?? null;
                }
            }
        }

        vitebskQty.value = Number((props.product as any).vitebsk_qty || 0);
        loadSupplierOffers();
    }
});

const loadSupplierOffers = async () => {
    if (!props.product) return;
    try {
        const res = await api.getProductSupplierOffers(props.product.id);
        supplierOffers.value = res.items || [];
    } catch (e) {
        console.error(e);
        supplierOffers.value = [];
    }
};

const addRow = () => specs.value.push({ key: '', value: '' });
const removeRow = (index: number) => specs.value.splice(index, 1);

const close = () => emit('update:modelValue', false);

const saveLocalStock = async () => {
    if (!props.product) return;
    localStockSaving.value = true;
    formMessage.value = '';
    try {
        await api.upsertProductLocalStock(props.product.id, { qty: Number(vitebskQty.value || 0) });
        emit('success');
    } catch (e) {
        formMessage.value = `Ошибка при обновлении склада: ${getApiErrorMessage(e)}`;
    } finally {
        localStockSaving.value = false;
    }
};

const save = async () => {
    if (!props.product) return;
    
    // Process specs back to object
    const validSpecs: Record<string, any> = {};
    for (const row of specs.value) {
        if (row.key.trim()) {
            let finalValue = row.value;
            const config = specsTranslations[row.key.trim()];
            if (config?.type === 'number' && config.unit && finalValue.toString().trim() !== '') {
                finalValue = `${finalValue} ${config.unit}`.trim();
            } else if (config?.type === 'boolean') {
                finalValue = (row.value === 'true') ? 'true' : 'false';
            }
            validSpecs[row.key.trim()] = finalValue.toString().trim();
        }
    }

    if (selectedBrandEntity.value) {
        validSpecs.brand = selectedBrandEntity.value.title;
        const group = brandGroup.value;
        if (group) {
            for (const tag of group.tags) {
                selectedTagIds.value.delete(tag.id);
            }
            const bySlug = group.tags.find((tag) => normalizeText(tag.slug) === normalizeText(selectedBrandEntity.value?.slug));
            const byTitle = group.tags.find((tag) => normalizeText(tag.title) === normalizeText(selectedBrandEntity.value?.title));
            const brandTag = bySlug || byTitle;
            if (brandTag) selectedTagIds.value.add(brandTag.id);
        }
    } else if (!selectedBrandTag.value) {
        delete validSpecs.brand;
        delete validSpecs['Бренд'];
        delete validSpecs['Марка'];
        delete validSpecs['Производитель'];
    }

    if (compatibilityIndoorSlugs.value.length > 0) {
        validSpecs[COMPATIBLE_INDOOR_KEY] = [...compatibilityIndoorSlugs.value];
    }
    if (compatibilityOutdoorSlugs.value.length > 0) {
        validSpecs[COMPATIBLE_OUTDOOR_KEY] = [...compatibilityOutdoorSlugs.value];
    }
    validSpecs[MULTI_COMPAT_MODE_KEY] = multiCompatMode.value;
    if (multiCompatMode.value === 'free_match') {
        if (normalizedCapacityCombos.value.length > 0) {
            validSpecs[MULTI_CAPACITY_COMBOS_KEY] = [...normalizedCapacityCombos.value];
        }
    } else {
        const serializedMultiRules = serializeMultiComboRules();
        if (serializedMultiRules.length > 0) {
            validSpecs[MULTI_COMBO_RULES_KEY] = serializedMultiRules;
        }
    }

    loading.value = true;
    formMessage.value = '';
    formServerErrors.value = {};
    try {
        const updateData = {
            ...form.value,
            brand_id: selectedBrandEntityId.value ?? null,
            specs: validSpecs,
            tag_ids: Array.from(selectedTagIds.value),
        };
        await api.updateProduct(props.product.id, updateData);
        emit('success');
        close();
    } catch (e) {
        const parsed = parseApiFieldErrors(e, [
            'title',
            'slug',
            'price',
            'old_price',
            'is_published',
            'brand_id',
            'specs',
            'tag_ids',
        ]);
        formServerErrors.value = parsed.fieldErrors;
        formMessage.value = parsed.message || `Ошибка при сохранении: ${getApiErrorMessage(e)}`;
        console.error(e);
    } finally {
        loading.value = false;
    }
};

const unlinkSupplierOffer = async (offer: any) => {
    const mappingId = Number(offer?.mapping_id || 0);
    if (!mappingId) return;
    if (!confirm('Отвязать этот прайс от товара?')) return;
    unlinkingMappingId.value = mappingId;
    formMessage.value = '';
    try {
        await api.deleteSupplierMapping(mappingId);
        await loadSupplierOffers();
        emit('success');
    } catch (e) {
        formMessage.value = `Ошибка при отвязке: ${getApiErrorMessage(e)}`;
    } finally {
        unlinkingMappingId.value = null;
    }
};
</script>

<template>
    <div v-if="modelValue" class="product-edit-modal fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60] p-4" @click.self="close">
        <div class="bg-slate-50 dark:bg-slate-900 rounded-2xl w-full max-w-5xl flex flex-col max-h-[90vh] shadow-2xl border border-gray-100 dark:border-slate-800 overflow-hidden">
            <!-- Header -->
            <header class="p-5 border-b dark:border-slate-800 flex justify-between items-center bg-slate-100/50 dark:bg-slate-800/50">
                <div class="flex items-center gap-3">
                    <div class="p-2 bg-teal-100 rounded-lg text-teal-700">
                        <Edit3 class="w-5 h-5" />
                    </div>
                    <div>
                        <h2 class="text-lg font-bold text-gray-900 dark:text-white">Редактирование товара</h2>
                        <p class="text-xs text-gray-500 dark:text-slate-400 font-medium uppercase tracking-wider">ID: {{ product?.id }}</p>
                    </div>
                </div>
                <button @click="close" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all">
                    <X class="w-5 h-5" />
                </button>
            </header>
            <div v-if="formMessage" class="mx-6 mt-4 rounded-xl border border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">
                {{ formMessage }}
            </div>
            
            <div class="flex-1 overflow-y-auto p-6">
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Column 1: Basic Info -->
                    <section class="space-y-5">
                        <h3 class="text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest">Основные данные</h3>
                        
                        <div>
                            <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Название модели</label>
                            <input 
                                v-model="form.title" 
                                type="text"
                                class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-gray-900 dark:text-slate-100 font-medium text-sm"
                                :class="formServerErrors.title ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                placeholder="Напр: LG ARTCOOL Gallery"
                            />
                            <p v-if="formServerErrors.title" class="mt-1 text-xs text-red-600">{{ formServerErrors.title }}</p>
                        </div>

                        <div>
                            <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1 flex justify-between items-center">
                                <span>Slug (URL путь)</span>
                                <Globe class="w-3.5 h-3.5 text-gray-400 dark:text-slate-500" />
                            </label>
                            <input 
                                v-model="form.slug" 
                                type="text"
                                class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-sm font-mono text-gray-600 dark:text-slate-300"
                                :class="formServerErrors.slug ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                placeholder="lg-artcool-gallery"
                            />
                            <p v-if="formServerErrors.slug" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ formServerErrors.slug }}</p>
                        </div>

                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Цена (BYN)</label>
                                <div class="relative">
                                    <input 
                                        v-model.number="form.price" 
                                        type="number"
                                        class="w-full pl-3 pr-10 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all font-bold text-teal-700 dark:text-teal-400 text-sm"
                                        :class="formServerErrors.price ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                    />
                                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 text-xs">руб.</span>
                                </div>
                                <p v-if="formServerErrors.price" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ formServerErrors.price }}</p>
                            </div>
                            <div>
                                <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1 line-through decoration-gray-400 dark:decoration-slate-600">Старая цена</label>
                                <div class="relative">
                                    <input 
                                        v-model.number="form.old_price" 
                                        type="number"
                                        class="w-full pl-3 pr-10 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-gray-500 dark:text-slate-400 text-sm"
                                        :class="formServerErrors.old_price ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                    />
                                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 text-xs">руб.</span>
                                </div>
                                <p v-if="formServerErrors.old_price" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ formServerErrors.old_price }}</p>
                            </div>
                        </div>

                        <div class="flex items-center gap-2 pt-1">
                             <label class="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" v-model="form.is_published" class="sr-only peer">
                                <div class="w-11 h-6 bg-gray-200 dark:bg-slate-700 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-900 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 dark:after:border-slate-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-600"></div>
                                <span class="ms-3 text-sm font-semibold text-gray-700 dark:text-slate-300">Опубликовано</span>
                            </label>
                        </div>

                        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 space-y-3">
                            <h4 class="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">Supply</h4>
                            <div class="flex items-end gap-2">
                                <div class="flex-1">
                                    <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Склад Витебск (шт)</label>
                                    <input v-model.number="vitebskQty" type="number" min="0" class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-xl text-sm" />
                                </div>
                                <button
                                    @click="saveLocalStock"
                                    :disabled="localStockSaving"
                                    class="px-3 py-2 rounded-xl bg-teal-600 text-white text-sm font-semibold disabled:opacity-50"
                                >
                                    {{ localStockSaving ? 'Сохранение...' : 'Сохранить' }}
                                </button>
                            </div>
                            <div class="max-h-40 overflow-y-auto space-y-2">
                                <div v-if="supplierOffers.length === 0" class="text-xs text-gray-500 dark:text-slate-400">Нет привязанных офферов</div>
                                <div v-for="offer in supplierOffers" :key="`${offer.supplier_id}-${offer.external_id}`" class="text-xs border border-gray-100 dark:border-slate-700 rounded-lg p-2 bg-slate-50 dark:bg-slate-900/40">
                                    <div class="flex items-start justify-between gap-2">
                                        <div class="font-semibold text-gray-700 dark:text-slate-200">{{ offer.supplier_name || offer.supplier_id }} / {{ offer.external_id }}</div>
                                        <button
                                            v-if="offer.mapping_id"
                                            @click="unlinkSupplierOffer(offer)"
                                            :disabled="unlinkingMappingId === offer.mapping_id"
                                            class="px-2 py-1 rounded border border-red-300 text-red-600 text-[11px] font-semibold disabled:opacity-50"
                                        >
                                            {{ unlinkingMappingId === offer.mapping_id ? '...' : 'Отвязать' }}
                                        </button>
                                    </div>
                                    <div class="text-gray-500 dark:text-slate-400">
                                        qty: {{ offer.qty }} | wholesale: {{ offer.wholesale_value ?? '—' }} {{ offer.wholesale_currency || '' }} | rrc: {{ offer.rrc_byn ?? '—' }}
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div
                            v-if="isCurrentProductMulti"
                            class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 space-y-3"
                        >
                            <h4 class="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">Быстрые пресеты</h4>
                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-teal-200 text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/20 text-xs font-semibold text-left"
                                    @click="applyPreset('multi_outdoor')"
                                >
                                    Мульти: наружный блок
                                </button>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-teal-200 text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/20 text-xs font-semibold text-left"
                                    @click="applyPreset('multi_indoor')"
                                >
                                    Мульти: внутренний блок
                                </button>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-indigo-200 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/20 text-xs font-semibold text-left"
                                    @click="applyPreset('semi_cassette')"
                                >
                                    Полупром: кассетный
                                </button>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-indigo-200 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/20 text-xs font-semibold text-left"
                                    @click="applyPreset('semi_duct')"
                                >
                                    Полупром: канальный
                                </button>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-indigo-200 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/20 text-xs font-semibold text-left"
                                    @click="applyPreset('semi_floor_ceiling')"
                                >
                                    Полупром: напольно-потолочный
                                </button>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-indigo-200 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-900/20 text-xs font-semibold text-left"
                                    @click="applyPreset('semi_column')"
                                >
                                    Полупром: колонный
                                </button>
                            </div>
                        </div>

                        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 space-y-3">
                            <h4 class="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">Бренд</h4>
                            <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-start">
                                <select
                                    class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg text-sm"
                                    :value="selectedBrandEntityId ?? ''"
                                    :disabled="brandsLoading"
                                    @change="onBrandEntitySelectChange"
                                >
                                    <option value="">{{ brandsLoading ? 'Загрузка брендов...' : 'Не выбран' }}</option>
                                    <option v-for="brand in brandOptions" :key="brand.id" :value="brand.id">
                                        {{ brand.title }}
                                    </option>
                                </select>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 text-xs font-semibold whitespace-nowrap"
                                    @click="applyBrandEntitySelection(null)"
                                >
                                    Очистить
                                </button>
                            </div>
                            <p class="text-[11px] text-gray-500 dark:text-slate-400">
                                Канонический источник бренда: <code>product.brand_id</code>.
                            </p>
                            <div class="h-px bg-gray-100 dark:bg-slate-700"></div>
                            <p class="text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500">
                                Совместимость (brand tag)
                            </p>
                            <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-start">
                                <select
                                    class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg text-sm"
                                    :value="selectedBrandTagId ?? ''"
                                    @change="onBrandSelectChange"
                                >
                                    <option value="">Не выбран</option>
                                    <option v-for="tag in brandTagsSorted" :key="tag.id" :value="tag.id">
                                        {{ tag.title }}
                                    </option>
                                </select>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 text-xs font-semibold whitespace-nowrap"
                                    @click="applyBrandEntitySelection(null)"
                                >
                                    Очистить
                                </button>
                            </div>
                            <div class="flex gap-2">
                                <input
                                    v-model="newBrandTitle"
                                    type="text"
                                    placeholder="Новый бренд (например TCL)"
                                    class="flex-1 px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg text-sm"
                                    @keyup.enter="createAndSelectBrand"
                                />
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-teal-200 dark:border-teal-800 text-sm font-semibold text-teal-700 dark:text-teal-300 disabled:opacity-50"
                                    :disabled="creatingBrand"
                                    @click="createAndSelectBrand"
                                >
                                    {{ creatingBrand ? 'Создание...' : 'Создать и выбрать' }}
                                </button>
                            </div>
                            <p class="text-[11px] text-gray-500 dark:text-slate-400">
                                При выборе бренда мы синхронизируем <code>brand_id</code>, тег группы <code>brand</code> и <code>specs.brand</code>.
                            </p>
                        </div>

                        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 space-y-3">
                            <div class="flex items-start justify-between gap-2">
                                <h4 class="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">Совместимость мульти</h4>
                                <div class="text-[11px] text-gray-500 dark:text-slate-400 text-right">
                                    <div>
                                        Роль: {{
                                            currentProductRole === 'indoor'
                                                ? 'внутренний'
                                                : currentProductRole === 'outdoor'
                                                    ? 'наружный'
                                                    : 'не определена'
                                        }}
                                    </div>
                                    <div>
                                        Бренд: {{ currentBrandTitle || 'не задан' }}
                                    </div>
                                </div>
                            </div>

                            <div class="flex gap-2">
                                <input
                                    v-model="compatibilityQuery"
                                    type="text"
                                    placeholder="Найти мульти-товары (например TCL FMA)"
                                    class="flex-1 px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg text-sm"
                                    @keyup.enter="searchCompatibilityProducts"
                                />
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 text-sm font-semibold"
                                    :disabled="compatibilityLoading"
                                    @click="searchCompatibilityProducts"
                                >
                                    {{ compatibilityLoading ? '...' : 'Поиск' }}
                                </button>
                                <button
                                    type="button"
                                    class="px-3 py-2 rounded-lg border border-teal-200 dark:border-teal-800 text-sm font-semibold text-teal-700 dark:text-teal-300 disabled:opacity-50"
                                    :disabled="compatibilityLoading || !hasBrandContext"
                                    @click="autoFillCompatibilityByBrand"
                                >
                                    Авто по бренду
                                </button>
                            </div>
                            <div v-if="compatibilityInfo" class="text-[11px] text-gray-500 dark:text-slate-400">
                                {{ compatibilityInfo }}
                            </div>

                            <div v-if="compatibilityResults.length > 0" class="max-h-40 overflow-y-auto space-y-2">
                                <div
                                    v-for="candidate in compatibilityResults"
                                    :key="candidate.id"
                                    class="rounded-lg border border-gray-100 dark:border-slate-700 p-2 bg-slate-50 dark:bg-slate-900/40"
                                >
                                    <div class="text-xs font-semibold text-gray-700 dark:text-slate-200">{{ candidate.title }}</div>
                                    <div class="text-[11px] text-gray-500 dark:text-slate-400 mb-2">{{ candidate.slug }}</div>
                                    <div class="flex flex-wrap gap-1.5">
                                        <button
                                            type="button"
                                            class="px-2 py-1 rounded border border-indigo-300 text-indigo-700 text-[11px] font-semibold"
                                            :disabled="!candidate.slug"
                                            @click="addCompatibilitySlug('indoor', candidate.slug || '')"
                                        >
                                            В совместимые внутренние
                                        </button>
                                        <button
                                            type="button"
                                            class="px-2 py-1 rounded border border-teal-300 text-teal-700 text-[11px] font-semibold"
                                            :disabled="!candidate.slug"
                                            @click="addCompatibilitySlug('outdoor', candidate.slug || '')"
                                        >
                                            В совместимые наружные
                                        </button>
                                    </div>
                                </div>
                            </div>

                            <div class="space-y-2">
                                <div>
                                    <p class="text-[11px] font-bold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-1">Совместимые внутренние (для наружного)</p>
                                    <div class="flex flex-wrap gap-1.5">
                                        <span
                                            v-for="slug in compatibilityIndoorSlugs"
                                            :key="`indoor-${slug}`"
                                            class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-indigo-100 text-indigo-800 text-[11px] font-semibold"
                                        >
                                            {{ slug }}
                                            <button type="button" class="text-indigo-700" @click="removeCompatibilitySlug('indoor', slug)">×</button>
                                        </span>
                                        <span v-if="compatibilityIndoorSlugs.length === 0" class="text-[11px] text-gray-400">Не задано</span>
                                    </div>
                                </div>
                                <div>
                                    <p class="text-[11px] font-bold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-1">Совместимые наружные (для внутреннего)</p>
                                    <div class="flex flex-wrap gap-1.5">
                                        <span
                                            v-for="slug in compatibilityOutdoorSlugs"
                                            :key="`outdoor-${slug}`"
                                            class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-teal-100 text-teal-800 text-[11px] font-semibold"
                                        >
                                            {{ slug }}
                                            <button type="button" class="text-teal-700" @click="removeCompatibilitySlug('outdoor', slug)">×</button>
                                        </span>
                                        <span v-if="compatibilityOutdoorSlugs.length === 0" class="text-[11px] text-gray-400">Не задано</span>
                                    </div>
                                </div>
                            </div>

                            <div v-if="currentProductRole === 'outdoor'" class="rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/30 p-3 space-y-2">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                                        Режим совместимости мульти
                                    </p>
                                </div>

                                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                    <label class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-slate-300 rounded border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-2 cursor-pointer">
                                        <input
                                            v-model="multiCompatMode"
                                            type="radio"
                                            value="free_match"
                                            class="accent-teal-600"
                                        />
                                        <span>
                                            <strong>Free Match (по умолчанию)</strong><br />
                                            По таблице мощностей: 09+09, 09+12 и т.д.
                                        </span>
                                    </label>
                                    <label class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-slate-300 rounded border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-2 cursor-pointer">
                                        <input
                                            v-model="multiCompatMode"
                                            type="radio"
                                            value="strict"
                                            class="accent-indigo-600"
                                        />
                                        <span>
                                            <strong>Строгий</strong><br />
                                            Только точные наборы моделей (slug+qty).
                                        </span>
                                    </label>
                                </div>

                                <div v-if="multiCompatMode === 'free_match'" class="rounded-lg border border-teal-200 dark:border-teal-800/50 bg-white dark:bg-slate-900 p-2.5 space-y-2">
                                    <p class="text-[11px] text-gray-500 dark:text-slate-400">
                                        Введите допустимые комбинации через запятую или с новой строки. Пример: <code>09+09, 09+12, 12+12</code>
                                    </p>
                                    <textarea
                                        v-model="capacityCombosInput"
                                        rows="3"
                                        placeholder="09+09, 09+12, 12+12"
                                        class="w-full px-2.5 py-2 bg-slate-100 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded text-xs"
                                    />
                                    <div class="flex flex-wrap gap-1.5">
                                        <span
                                            v-for="combo in normalizedCapacityCombos"
                                            :key="combo"
                                            class="inline-flex items-center px-2 py-1 rounded-full bg-teal-100 text-teal-800 text-[11px] font-semibold"
                                        >
                                            {{ combo }}
                                        </span>
                                        <span v-if="normalizedCapacityCombos.length === 0" class="text-[11px] text-gray-400">
                                            Комбинации не заданы. Будет fallback-проверка по портам/бренду.
                                        </span>
                                    </div>
                                </div>

                                <div v-else class="space-y-2">
                                    <div class="flex items-center justify-between gap-2">
                                        <p class="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400">
                                            Точные конфигурации (slug)
                                        </p>
                                        <button
                                            type="button"
                                            class="px-2.5 py-1 rounded border border-teal-300 dark:border-teal-800 text-teal-700 dark:text-teal-300 text-[11px] font-semibold"
                                            @click="addMultiComboRule"
                                        >
                                            + Конфигурация
                                        </button>
                                    </div>
                                    <p class="text-[11px] text-gray-500 dark:text-slate-400">
                                        Используйте только если нужны жестко фиксированные наборы конкретных внутренних моделей.
                                    </p>

                                    <div v-if="multiComboRules.length === 0" class="text-[11px] text-gray-400">
                                        Строгие конфигурации не заданы.
                                    </div>

                                    <div v-for="rule in multiComboRules" :key="rule.id" class="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2.5 space-y-2">
                                        <div class="flex items-center gap-2">
                                            <input
                                                v-model="rule.title"
                                                type="text"
                                                placeholder="Название (например 09+12)"
                                                class="flex-1 px-2.5 py-1.5 bg-slate-100 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded text-xs"
                                            />
                                            <button
                                                type="button"
                                                class="px-2 py-1 rounded border border-red-300 dark:border-red-800 text-red-600 dark:text-red-300 text-[11px] font-semibold"
                                                @click="removeMultiComboRule(rule.id)"
                                            >
                                                Удалить
                                            </button>
                                        </div>

                                        <div class="space-y-1.5">
                                            <div v-for="(line, lineIndex) in rule.lines" :key="`${rule.id}-${lineIndex}`" class="grid grid-cols-[1fr_84px_auto] gap-1.5 items-center">
                                                <input
                                                    v-model="line.slug"
                                                    list="multi-indoor-slugs"
                                                    type="text"
                                                    placeholder="slug внутреннего блока"
                                                    class="px-2.5 py-1.5 bg-slate-100 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded text-xs"
                                                />
                                                <input
                                                    v-model.number="line.qty"
                                                    type="number"
                                                    min="1"
                                                    step="1"
                                                    class="px-2 py-1.5 bg-slate-100 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded text-xs text-center"
                                                />
                                                <button
                                                    type="button"
                                                    class="px-2 py-1 rounded border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 text-[11px] font-semibold"
                                                    @click="removeMultiComboRuleLine(rule.id, lineIndex)"
                                                >
                                                    ×
                                                </button>
                                            </div>
                                        </div>

                                        <div class="flex items-center gap-2">
                                            <button
                                                type="button"
                                                class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-[11px] font-semibold"
                                                @click="addMultiComboRuleLine(rule.id)"
                                            >
                                                + Блок
                                            </button>
                                            <button
                                                type="button"
                                                class="px-2.5 py-1 rounded border border-indigo-300 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 text-[11px] font-semibold disabled:opacity-50"
                                                :disabled="compatibilityIndoorSlugs.length === 0"
                                                @click="fillRuleFromIndoorCompatibility(rule.id)"
                                            >
                                                Заполнить из совместимых
                                            </button>
                                            <span class="text-[11px] text-gray-500 dark:text-slate-400 truncate">
                                                {{ getRulePreview(rule) || '—' }}
                                            </span>
                                        </div>
                                    </div>

                                    <datalist id="multi-indoor-slugs">
                                        <option v-for="slug in indoorSlugOptions" :key="slug" :value="slug" />
                                    </datalist>
                                </div>
                            </div>
                        </div>
                    </section>

                    <!-- Column 2: Specs -->
                    <section class="space-y-5">
                        <div class="flex justify-between items-center">
                            <h3 class="text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                                 Характеристики
                            </h3>
                            <button @click="addRow" class="text-xs bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 px-2.5 py-1 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700 text-teal-600 dark:text-teal-400 font-bold flex items-center gap-1 transition-colors shadow-sm">
                                <Plus class="w-3 h-3" /> Добавить
                            </button>
                        </div>

                        <div class="space-y-2 bg-slate-100/50 dark:bg-slate-800/50 p-3 rounded-2xl border border-gray-100 dark:border-slate-800 max-h-[400px] overflow-y-auto">
                            <div v-for="(row, idx) in specs" :key="idx" class="flex gap-1.5 items-start group">
                                <div class="relative flex-1">
                                    <SpecKeyCombobox 
                                        v-model="row.key" 
                                        :known-keys="knownKeys" 
                                    />
                                </div>
                                
                                <div class="flex-1">
                                    <template v-if="specsTranslations[row.key]?.type === 'boolean'">
                                        <div class="flex items-center h-[38px]">
                                            <button 
                                                type="button"
                                                @click="row.value = (row.value === 'true') ? 'false' : 'true'"
                                                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2"
                                                :class="(row.value === 'true') ? 'bg-teal-600' : 'bg-gray-200 dark:bg-slate-700'"
                                                role="switch"
                                                :aria-checked="row.value === 'true'"
                                            >
                                                <span class="sr-only">Toggle boolean</span>
                                                <span 
                                                    aria-hidden="true" 
                                                    class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                                                    :class="(row.value === 'true') ? 'translate-x-5' : 'translate-x-0'"
                                                />
                                            </button>
                                            <span class="ml-3 text-sm font-medium text-gray-900 dark:text-slate-200">
                                                {{ (row.value === 'true') ? 'Да' : 'Нет' }}
                                            </span>
                                        </div>
                                    </template>
                                    
                                    <template v-else-if="specsTranslations[row.key]?.type === 'select'">
                                        <select 
                                            v-model="row.value"
                                            class="w-full h-[38px] border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all text-gray-900 dark:text-slate-200 shadow-inner"
                                        >
                                            <option value="" disabled>Выберите значение</option>
                                            <option v-for="opt in specsTranslations[row.key]?.options || []" :key="opt" :value="opt">
                                                {{
                                                    row.key === 'wifi_ready'
                                                        ? (opt === 'true' ? 'Да (встроен)' : (opt === 'ready' ? 'Ready (модуль отдельно)' : 'Нет'))
                                                        : opt
                                                }}
                                            </option>
                                        </select>
                                    </template>
                                    
                                    <template v-else-if="specsTranslations[row.key]?.type === 'number'">
                                        <div class="flex h-[38px] rounded-lg shadow-inner">
                                            <input 
                                                type="number"
                                                v-model="row.value" 
                                                placeholder="Значение" 
                                                class="flex-1 min-w-0 block w-full border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-gray-900 dark:text-slate-200 rounded-none rounded-l-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all"
                                            />
                                            <span v-if="specsTranslations[row.key]?.unit" class="inline-flex items-center px-2.5 rounded-r-lg border border-l-0 border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-700 text-gray-500 dark:text-slate-300 text-xs">
                                                {{ specsTranslations[row.key]?.unit }}
                                            </span>
                                        </div>
                                    </template>
                                    
                                    <template v-else>
                                        <input 
                                            type="text"
                                            v-model="row.value" 
                                            placeholder="Значение" 
                                            class="w-full h-[38px] border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all text-gray-900 dark:text-slate-200 dark:placeholder-slate-500 shadow-inner"
                                        />
                                    </template>
                                </div>
                                
                                <button @click="removeRow(idx)" class="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all">
                                    <Trash2 class="w-3.5 h-3.5" />
                                </button>
                            </div>
                            
                            <div v-if="specs.length === 0" class="text-center py-6 text-gray-400 dark:text-slate-500">
                                 <Hash class="w-6 h-6 mx-auto mb-1.5 opacity-20" />
                                 <p class="text-xs">Нет характеристик</p>
                            </div>
                        </div>
                    </section>
                </div>

                <details class="mt-6 border border-gray-200 dark:border-slate-700 rounded-xl bg-slate-50 dark:bg-slate-800/50 group">
                    <summary class="cursor-pointer p-4 font-bold text-gray-700 dark:text-slate-300 flex justify-between items-center outline-none">
                        <span class="flex items-center gap-2"><Tag class="w-4 h-4 text-gray-400 dark:text-slate-500"/> Теги ({{ selectedTagIds.size }} выбрано)</span>
                    </summary>
                    <div class="p-4 border-t border-gray-200 dark:border-slate-700">
                        <input 
                            v-model="tagSearchQuery"
                            type="text"
                            placeholder="Поиск тега..."
                            class="w-full mb-4 px-3 py-2 bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-xl focus:bg-white focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-sm dark:text-slate-200 dark:placeholder-slate-500"
                        />

                        <div class="bg-gray-50/50 dark:bg-slate-800/50 rounded-xl border border-gray-100 dark:border-slate-800 max-h-[300px] overflow-y-auto">
                            <div v-if="tagsLoading" class="p-6 text-center text-gray-400 text-sm">Загрузка...</div>
                            <div v-else-if="filteredTagGroups.length === 0" class="p-6 text-center text-gray-400 text-sm">Нет тегов</div>
                            <div v-else>
                                <div v-for="group in filteredTagGroups" :key="group.id" class="p-3 border-b border-gray-100 dark:border-slate-800 last:border-b-0">
                                    <p class="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">{{ group.title }}</p>
                                    <div class="flex flex-wrap gap-1.5">
                                        <button 
                                            v-for="tag in group.tags" 
                                            :key="tag.id"
                                            @click="toggleTag(tag.id, group)"
                                            class="px-2.5 py-1 rounded-full text-xs font-semibold border cursor-pointer transition-all"
                                            :class="isTagSelected(tag.id) ? getSelectedColorClasses(group.color) : getColorClasses(group.color)"
                                        >
                                            {{ tag.title }}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </details>
            </div>
            
            <!-- Footer -->
            <footer class="p-5 border-t dark:border-slate-800 bg-slate-100/50 dark:bg-slate-800/50 flex justify-end gap-3">
                <button @click="close" class="px-5 py-2 text-sm font-bold text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 rounded-xl transition-all">
                    Отмена
                </button>
                <button 
                    @click="save" 
                    :disabled="loading"
                    class="px-8 py-2 bg-teal-600 text-white rounded-xl shadow-lg shadow-teal-700/20 hover:bg-teal-700 disabled:opacity-50 flex items-center gap-2 text-sm font-bold transition-all transform hover:-translate-y-0.5 active:translate-y-0"
                >
                    <div v-if="loading" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    <Save v-else class="w-4 h-4" />
                    Сохранить
                </button>
            </footer>
        </div>
    </div>
</template>

<style scoped>
:global(.dark) .product-edit-modal .text-gray-400 {
  color: #94a3b8 !important;
}

:global(.dark) .product-edit-modal .text-gray-500 {
  color: #94a3b8 !important;
}

:global(.dark) .product-edit-modal .text-gray-600 {
  color: #cbd5e1 !important;
}

:global(.dark) .product-edit-modal .text-gray-700 {
  color: #e2e8f0 !important;
}

:global(.dark) .product-edit-modal .bg-gray-50\/50,
:global(.dark) .product-edit-modal .bg-gray-50 {
  background-color: #0f172a !important;
}

:global(.dark) .product-edit-modal .border-gray-100,
:global(.dark) .product-edit-modal .border-gray-200 {
  border-color: #334155 !important;
}

:global(.dark) .product-edit-modal footer button:first-child {
  color: #cbd5e1 !important;
}

:global(.dark) .product-edit-modal input::placeholder {
  color: #64748b !important;
}
</style>
