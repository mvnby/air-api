<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { X, Search, CheckSquare, Square, Link2 } from 'lucide-vue-next';
import { api, type Product } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const COMPATIBLE_INDOOR_KEY = 'compatible_indoor_slugs';
const COMPATIBLE_OUTDOOR_KEY = 'compatible_outdoor_slugs';

const props = defineProps<{
    modelValue: boolean;
    selectedProducts: Product[];
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const query = ref('');
const loadingCandidates = ref(false);
const applying = ref(false);
const info = ref('');
const error = ref('');
const candidates = ref<Product[]>([]);
const selectedCandidateSlugs = ref<Set<string>>(new Set());
const applyReverse = ref(false);

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

const getSpecsMap = (product: Product | null | undefined): Record<string, any> => (
    ((product as any)?.specs || {}) as Record<string, any>
);

const getBrandFromSpecs = (product: Product | null | undefined): string => {
    const specs = getSpecsMap(product);
    return String(specs.brand ?? specs['Бренд'] ?? specs['Марка'] ?? specs['Производитель'] ?? '').trim();
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

const isMultiRelatedProduct = (product: Product): boolean => {
    const tags = (product as any)?.tags || [];
    return tags.some((tag: any) => tag?.slug === 'cat-multi');
};

const getProductRole = (product: Product): 'indoor' | 'outdoor' | 'unknown' => {
    const specs = getSpecsMap(product);
    const typeText = normalizeText(specs.type ?? specs['Тип']);
    const titleText = normalizeText(product?.title);
    const joined = `${typeText} ${titleText}`;
    if (joined.includes('внутрен')) return 'indoor';
    if (joined.includes('наруж') || joined.includes('мульти-сплит')) return 'outdoor';
    return 'unknown';
};

const selectedMultiProducts = computed(() => props.selectedProducts.filter((item) => isMultiRelatedProduct(item)));
const selectedIds = computed(() => selectedMultiProducts.value.map((item) => item.id));
const selectedBaseSlugs = computed(() => selectedMultiProducts.value.map((item) => String(item.slug || '').trim()).filter(Boolean));

const selectedRole = computed<'indoor' | 'outdoor' | 'mixed' | 'unknown'>(() => {
    const roles = selectedMultiProducts.value.map((item) => getProductRole(item));
    if (roles.length === 0) return 'unknown';
    const hasIndoor = roles.includes('indoor');
    const hasOutdoor = roles.includes('outdoor');
    const hasUnknown = roles.includes('unknown');
    if (hasUnknown) return 'unknown';
    if (hasIndoor && hasOutdoor) return 'mixed';
    if (hasIndoor) return 'indoor';
    if (hasOutdoor) return 'outdoor';
    return 'unknown';
});

const selectedBrandIds = computed(() => {
    const raw = selectedMultiProducts.value
        .map((item) => Number((item as any)?.brand_id || 0))
        .filter((id) => Number.isFinite(id) && id > 0);
    return Array.from(new Set(raw));
});

const selectedBrandTokens = computed(() => {
    const tokens = selectedMultiProducts.value
        .filter((item) => Number((item as any)?.brand_id || 0) <= 0)
        .map((item) => getResolvedBrandToken(item))
        .filter(Boolean);
    return Array.from(new Set(tokens));
});

const hasBrandConflict = computed(() => (
    selectedBrandIds.value.length > 1
    || (selectedBrandIds.value.length === 0 && selectedBrandTokens.value.length > 1)
));
const selectedBrandId = computed<number | null>(() => (
    selectedBrandIds.value.length === 1 ? (selectedBrandIds.value[0] ?? null) : null
));
const selectedBrandName = computed<string>(() => {
    if (selectedBrandId.value) {
        const withId = selectedMultiProducts.value.find((item) => Number((item as any)?.brand_id || 0) === selectedBrandId.value);
        const resolved = getResolvedBrandName(withId);
        if (resolved) return resolved;
    }
    const names = selectedMultiProducts.value
        .filter((item) => Number((item as any)?.brand_id || 0) <= 0)
        .map((item) => getResolvedBrandName(item))
        .filter((name) => name.trim().length > 0);
    const unique = Array.from(new Set(names));
    if (unique.length === 1) return unique[0] ?? '';
    return '';
});
const selectedBrandToken = computed<string>(() => (
    selectedBrandTokens.value.length === 1 ? (selectedBrandTokens.value[0] ?? '') : ''
));

const oppositeRoleLabel = computed(() => (
    selectedRole.value === 'outdoor'
        ? 'внутренние блоки'
        : selectedRole.value === 'indoor'
            ? 'наружные блоки'
            : 'блоки'
));

const selectedRoleLabel = computed(() => (
    selectedRole.value === 'outdoor'
        ? 'наружные'
        : selectedRole.value === 'indoor'
            ? 'внутренние'
            : selectedRole.value === 'mixed'
                ? 'смешанные'
                : 'не определена'
));

const canUseModal = computed(() => (
    selectedMultiProducts.value.length > 0
    && (selectedRole.value === 'outdoor' || selectedRole.value === 'indoor')
    && !hasBrandConflict.value
));

const isSameBrandCandidate = (candidate: Product): boolean => {
    if (selectedBrandId.value) {
        const candidateBrandId = Number((candidate as any)?.brand_id || 0);
        return candidateBrandId > 0 && candidateBrandId === selectedBrandId.value;
    }

    const selectedToken = selectedBrandToken.value;
    if (selectedToken) {
        const candidateToken = getResolvedBrandToken(candidate);
        return Boolean(candidateToken) && candidateToken === selectedToken;
    }
    return true;
};

const isOppositeRoleCandidate = (candidate: Product): boolean => {
    const role = getProductRole(candidate);
    if (selectedRole.value === 'outdoor') return role === 'indoor';
    if (selectedRole.value === 'indoor') return role === 'outdoor';
    return false;
};

const filteredCandidates = computed(() => candidates.value.filter((item) => {
    if (!isMultiRelatedProduct(item)) return false;
    if (selectedIds.value.includes(item.id)) return false;
    if (!isOppositeRoleCandidate(item)) return false;
    if (!isSameBrandCandidate(item)) return false;
    return true;
}));

const selectedCandidateIds = computed(() => filteredCandidates.value
    .filter((item) => selectedCandidateSlugs.value.has(String(item.slug || '').trim()))
    .map((item) => item.id));

const selectAllCandidates = () => {
    selectedCandidateSlugs.value = new Set(
        filteredCandidates.value
            .map((item) => String(item.slug || '').trim())
            .filter(Boolean),
    );
};

const clearCandidateSelection = () => {
    selectedCandidateSlugs.value = new Set();
};

const toggleCandidate = (slug: string) => {
    const clean = slug.trim();
    if (!clean) return;
    const next = new Set(selectedCandidateSlugs.value);
    if (next.has(clean)) next.delete(clean);
    else next.add(clean);
    selectedCandidateSlugs.value = next;
};

const close = () => emit('update:modelValue', false);

const searchCandidates = async (seedOverride?: string) => {
    error.value = '';
    info.value = '';
    if (!canUseModal.value) return;

    const seed = String(seedOverride ?? query.value).trim();
    if (seed.length < 2) {
        error.value = 'Введите минимум 2 символа для поиска.';
        return;
    }

    loadingCandidates.value = true;
    try {
        const result = await api.smartSearchProducts(seed, 100);
        candidates.value = result;

        const allowed = new Set(
            filteredCandidates.value.map((item) => String(item.slug || '').trim()).filter(Boolean),
        );
        selectedCandidateSlugs.value = new Set(
            Array.from(selectedCandidateSlugs.value).filter((slug) => allowed.has(slug)),
        );

        info.value = `Найдено ${filteredCandidates.value.length} вариантов (${oppositeRoleLabel.value}) для выбранных товаров.`;
    } catch (e) {
        error.value = `Ошибка поиска: ${getApiErrorMessage(e)}`;
    } finally {
        loadingCandidates.value = false;
    }
};

const searchByBrand = async () => {
    const brandSeed = (selectedBrandName.value || selectedBrandToken.value || '').trim();
    if (!brandSeed) {
        error.value = 'У выбранных товаров не определен бренд (brand_id/specs/tag).';
        return;
    }
    query.value = brandSeed;
    await searchCandidates(brandSeed);
};

const applyCompatibility = async () => {
    error.value = '';
    info.value = '';
    if (!canUseModal.value) return;

    const candidateSlugs = Array.from(selectedCandidateSlugs.value).filter(Boolean);
    if (selectedIds.value.length === 0 || candidateSlugs.length === 0) {
        error.value = 'Выберите товары и хотя бы один совместимый блок.';
        return;
    }

    const targetKey = selectedRole.value === 'outdoor' ? COMPATIBLE_INDOOR_KEY : COMPATIBLE_OUTDOOR_KEY;
    const reverseKey = selectedRole.value === 'outdoor' ? COMPATIBLE_OUTDOOR_KEY : COMPATIBLE_INDOOR_KEY;

    applying.value = true;
    try {
        await api.bulkUpdateSpecs(selectedIds.value, { [targetKey]: candidateSlugs }, 'merge');

        if (applyReverse.value && selectedCandidateIds.value.length > 0 && selectedBaseSlugs.value.length > 0) {
            await api.bulkUpdateSpecs(selectedCandidateIds.value, { [reverseKey]: selectedBaseSlugs.value }, 'merge');
        }

        emit('success');
        close();
    } catch (e) {
        error.value = `Ошибка сохранения: ${getApiErrorMessage(e)}`;
    } finally {
        applying.value = false;
    }
};

watch(() => props.modelValue, async (opened) => {
    if (!opened) return;

    candidates.value = [];
    selectedCandidateSlugs.value = new Set();
    error.value = '';
    info.value = '';
    applyReverse.value = false;

    if (selectedBrandName.value) {
        query.value = selectedBrandName.value;
        await searchByBrand();
    } else {
        query.value = '';
    }
});
</script>

<template>
    <div v-if="modelValue" class="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" @click.self="close">
        <div class="w-full max-w-5xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
            <header class="px-5 py-4 border-b border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-between">
                <div>
                    <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">Массовая совместимость мульти-сплит</h2>
                    <p class="text-xs text-gray-500 dark:text-slate-400">
                        Выбрано: {{ selectedMultiProducts.length }} товаров · Роль: {{ selectedRoleLabel }}
                    </p>
                </div>
                <button
                    type="button"
                    class="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700"
                    @click="close"
                >
                    <X class="w-5 h-5" />
                </button>
            </header>

            <div class="p-5 space-y-4 max-h-[72vh] overflow-y-auto">
                <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 px-4 py-3 text-sm text-gray-700 dark:text-slate-300">
                    <div>Бренд: <span class="font-semibold">{{ selectedBrandName || (selectedBrandId ? `#${selectedBrandId}` : 'не определен') }}</span></div>
                    <div>Будем назначать: <span class="font-semibold">{{ oppositeRoleLabel }}</span></div>
                    <div class="text-xs mt-1 text-gray-500 dark:text-slate-400">
                        Операция перезаписывает ключ совместимости у выбранных товаров единым списком.
                    </div>
                </div>

                <div v-if="hasBrandConflict" class="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                    В выделении смешаны разные бренды. Выберите товары одного бренда.
                </div>
                <div v-else-if="selectedRole === 'mixed'" class="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                    Выделены и внутренние, и наружные блоки одновременно. Для массовой привязки оставьте один тип.
                </div>
                <div v-else-if="selectedRole === 'unknown'" class="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                    Не удалось определить тип выбранных товаров. Проверьте spec `type`.
                </div>

                <div class="flex gap-2">
                    <div class="relative flex-1">
                        <Search class="w-4 h-4 text-gray-400 dark:text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                        <input
                            v-model="query"
                            type="text"
                            class="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-gray-900 dark:text-slate-100"
                            :disabled="!canUseModal"
                            :placeholder="canUseModal ? 'Поиск кандидатов (например TCL FMA)' : 'Недоступно для текущего выделения'"
                            @keyup.enter="searchCandidates()"
                        />
                    </div>
                    <button
                        type="button"
                        class="px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-700 text-sm font-semibold text-gray-700 dark:text-slate-200 disabled:opacity-50"
                        :disabled="loadingCandidates || !canUseModal"
                        @click="searchCandidates()"
                    >
                        {{ loadingCandidates ? 'Поиск...' : 'Найти' }}
                    </button>
                    <button
                        type="button"
                        class="px-3 py-2 rounded-lg border border-teal-300 dark:border-teal-800 text-sm font-semibold text-teal-700 dark:text-teal-300 disabled:opacity-50"
                        :disabled="loadingCandidates || !canUseModal"
                        @click="searchByBrand"
                    >
                        По бренду
                    </button>
                </div>

                <div v-if="error" class="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                    {{ error }}
                </div>
                <div v-if="info" class="rounded-lg border border-teal-200 dark:border-teal-900/40 bg-teal-50 dark:bg-teal-900/20 px-3 py-2 text-sm text-teal-700 dark:text-teal-300">
                    {{ info }}
                </div>

                <div class="flex items-center justify-between">
                    <div class="text-sm text-gray-600 dark:text-slate-300">
                        Кандидаты: {{ filteredCandidates.length }}
                    </div>
                    <div class="flex items-center gap-2">
                        <button
                            type="button"
                            class="px-2.5 py-1.5 text-xs rounded border border-gray-300 dark:border-slate-700 text-gray-700 dark:text-slate-200 disabled:opacity-50"
                            :disabled="filteredCandidates.length === 0"
                            @click="selectAllCandidates"
                        >
                            Выбрать все
                        </button>
                        <button
                            type="button"
                            class="px-2.5 py-1.5 text-xs rounded border border-gray-300 dark:border-slate-700 text-gray-700 dark:text-slate-200 disabled:opacity-50"
                            :disabled="selectedCandidateSlugs.size === 0"
                            @click="clearCandidateSelection"
                        >
                            Сбросить
                        </button>
                    </div>
                </div>

                <div class="rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden">
                    <div v-if="filteredCandidates.length === 0" class="p-4 text-sm text-gray-500 dark:text-slate-400">
                        Пока нет кандидатов. Нажмите «По бренду» или выполните поиск.
                    </div>
                    <div v-else class="max-h-72 overflow-y-auto divide-y divide-gray-100 dark:divide-slate-700">
                        <label
                            v-for="candidate in filteredCandidates"
                            :key="candidate.id"
                            class="flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-800"
                        >
                            <button
                                type="button"
                                class="mt-0.5 text-gray-400 hover:text-teal-600"
                                @click.prevent="toggleCandidate(String(candidate.slug || ''))"
                            >
                                <CheckSquare v-if="selectedCandidateSlugs.has(String(candidate.slug || '').trim())" class="w-5 h-5 text-teal-600" />
                                <Square v-else class="w-5 h-5" />
                            </button>
                            <div class="min-w-0">
                                <div class="text-sm font-semibold text-gray-800 dark:text-slate-200 truncate">{{ candidate.title }}</div>
                                <div class="text-xs text-gray-500 dark:text-slate-400 truncate">
                                    {{ candidate.slug }} · {{ getProductRole(candidate) === 'indoor' ? 'внутренний' : 'наружный' }}
                                </div>
                            </div>
                        </label>
                    </div>
                </div>

                <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300">
                    <input v-model="applyReverse" type="checkbox" class="rounded border-gray-300 dark:border-slate-700 text-teal-600 focus:ring-teal-500" />
                    <span>
                        Записать обратные связи тоже
                        <span class="text-xs text-gray-500 dark:text-slate-400">
                            ({{ selectedRole === 'outdoor' ? 'у выбранных внутренних' : 'у выбранных наружных' }})
                        </span>
                    </span>
                </label>
            </div>

            <footer class="px-5 py-4 border-t border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-between">
                <div class="text-xs text-gray-500 dark:text-slate-400 flex items-center gap-1.5">
                    <Link2 class="w-3.5 h-3.5" />
                    Выбрано кандидатов: {{ selectedCandidateSlugs.size }}
                </div>
                <div class="flex items-center gap-2">
                    <button
                        type="button"
                        class="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700"
                        @click="close"
                    >
                        Отмена
                    </button>
                    <button
                        type="button"
                        class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50"
                        :disabled="applying || !canUseModal || selectedCandidateSlugs.size === 0 || selectedIds.length === 0"
                        @click="applyCompatibility"
                    >
                        {{ applying ? 'Применение...' : 'Применить' }}
                    </button>
                </div>
            </footer>
        </div>
    </div>
</template>
