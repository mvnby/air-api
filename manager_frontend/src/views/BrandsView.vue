<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, type ManagerBrand, type ManagerBrandSeries } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

type BrandForm = {
    title: string;
    slug: string;
    logo_url: string;
    description: string;
    sort_order: number;
    is_published: boolean;
};

type SeriesForm = {
    title: string;
    slug: string;
    description: string;
    hero_image: string;
    featuresText: string;
    sort_order: number;
    is_published: boolean;
};

const brands = ref<ManagerBrand[]>([]);
const loading = ref(true);
const saving = ref(false);
const query = ref('');
const error = ref('');
const toast = ref('');
const modalOpen = ref(false);
const editingBrand = ref<ManagerBrand | null>(null);
const selectedBrandId = ref<number | null>(null);
const seriesItems = ref<ManagerBrandSeries[]>([]);
const seriesLoading = ref(false);
const seriesSaving = ref(false);
const seriesError = ref('');
const seriesModalOpen = ref(false);
const editingSeries = ref<ManagerBrandSeries | null>(null);
const form = ref<BrandForm>({
    title: '',
    slug: '',
    logo_url: '',
    description: '',
    sort_order: 0,
    is_published: true,
});
const seriesForm = ref<SeriesForm>({
    title: '',
    slug: '',
    description: '',
    hero_image: '',
    featuresText: '',
    sort_order: 0,
    is_published: true,
});

const filteredBrands = computed(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return brands.value;
    return brands.value.filter((item) => {
        return (
            String(item.title || '').toLowerCase().includes(q)
            || String(item.slug || '').toLowerCase().includes(q)
        );
    });
});

const selectedBrand = computed(() => {
    if (!selectedBrandId.value) return null;
    return brands.value.find((item) => item.id === selectedBrandId.value) || null;
});

const resetForm = () => {
    form.value = {
        title: '',
        slug: '',
        logo_url: '',
        description: '',
        sort_order: 0,
        is_published: true,
    };
};

const resetSeriesForm = () => {
    seriesForm.value = {
        title: '',
        slug: '',
        description: '',
        hero_image: '',
        featuresText: '',
        sort_order: 0,
        is_published: true,
    };
};

const setToast = (message: string) => {
    toast.value = message;
    window.setTimeout(() => {
        if (toast.value === message) toast.value = '';
    }, 3000);
};

const fetchBrands = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerBrands();
        brands.value = [...(res.items || [])];
        if (selectedBrandId.value && !brands.value.some((item) => item.id === selectedBrandId.value)) {
            selectedBrandId.value = null;
        }
        if (!selectedBrandId.value && brands.value.length > 0) {
            selectedBrandId.value = brands.value[0]?.id || null;
        }
    } catch (err) {
        error.value = getApiErrorMessage(err);
    } finally {
        loading.value = false;
    }
};

const fetchSeries = async () => {
    if (!selectedBrandId.value) {
        seriesItems.value = [];
        return;
    }

    seriesLoading.value = true;
    seriesError.value = '';
    try {
        const res = await api.listManagerBrandSeries(selectedBrandId.value);
        seriesItems.value = [...(res.items || [])];
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    } finally {
        seriesLoading.value = false;
    }
};

const selectBrand = (brand: ManagerBrand) => {
    selectedBrandId.value = brand.id;
};

const openCreate = () => {
    editingBrand.value = null;
    resetForm();
    modalOpen.value = true;
    error.value = '';
};

const openEdit = (brand: ManagerBrand) => {
    editingBrand.value = brand;
    form.value = {
        title: String(brand.title || ''),
        slug: String(brand.slug || ''),
        logo_url: String(brand.logo_url || ''),
        description: String(brand.description || ''),
        sort_order: Number(brand.sort_order || 0),
        is_published: Boolean(brand.is_published),
    };
    modalOpen.value = true;
    error.value = '';
};

const closeModal = () => {
    modalOpen.value = false;
    editingBrand.value = null;
    resetForm();
};

const openSeriesCreate = () => {
    editingSeries.value = null;
    resetSeriesForm();
    seriesModalOpen.value = true;
    seriesError.value = '';
};

const openSeriesEdit = (series: ManagerBrandSeries) => {
    editingSeries.value = series;
    seriesForm.value = {
        title: String(series.title || ''),
        slug: String(series.slug || ''),
        description: String(series.description || ''),
        hero_image: String(series.hero_image || ''),
        featuresText: (series.features || []).join('\n'),
        sort_order: Number(series.sort_order || 0),
        is_published: Boolean(series.is_published),
    };
    seriesModalOpen.value = true;
    seriesError.value = '';
};

const closeSeriesModal = () => {
    seriesModalOpen.value = false;
    editingSeries.value = null;
    resetSeriesForm();
};

const normalizeFeatures = (value: string) => {
    const seen = new Set<string>();
    return String(value || '')
        .split('\n')
        .map((item) => item.trim())
        .filter((item) => {
            if (!item) return false;
            const key = item.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
};

const saveBrand = async () => {
    const title = String(form.value.title || '').trim();
    if (!title) {
        error.value = 'Название бренда обязательно.';
        return;
    }

    saving.value = true;
    error.value = '';
    try {
        const wasEditing = Boolean(editingBrand.value?.id);
        const payload = {
            title,
            slug: String(form.value.slug || '').trim() || undefined,
            logo_url: String(form.value.logo_url || '').trim() || undefined,
            description: String(form.value.description || '').trim() || undefined,
            sort_order: Number(form.value.sort_order || 0),
            is_published: Boolean(form.value.is_published),
        };
        if (editingBrand.value?.id) {
            await api.updateManagerBrand(editingBrand.value.id, payload);
        } else {
            await api.createManagerBrand(payload);
        }
        await fetchBrands();
        closeModal();
        setToast(wasEditing ? 'Бренд обновлен' : 'Бренд создан');
    } catch (err) {
        error.value = getApiErrorMessage(err);
    } finally {
        saving.value = false;
    }
};

const deleteBrand = async (brand: ManagerBrand) => {
    if (!confirm(`Удалить бренд "${brand.title}"?`)) return;
    error.value = '';
    try {
        await api.deleteManagerBrand(brand.id);
        await fetchBrands();
        setToast('Бренд удален');
    } catch (err) {
        error.value = getApiErrorMessage(err);
    }
};

const saveSeries = async () => {
    if (!selectedBrandId.value) return;

    const title = String(seriesForm.value.title || '').trim();
    if (!title) {
        seriesError.value = 'Название серии обязательно.';
        return;
    }

    seriesSaving.value = true;
    seriesError.value = '';
    try {
        const wasEditing = Boolean(editingSeries.value?.id);
        const payload = {
            title,
            slug: String(seriesForm.value.slug || '').trim() || undefined,
            description: String(seriesForm.value.description || '').trim() || undefined,
            hero_image: String(seriesForm.value.hero_image || '').trim() || undefined,
            features: normalizeFeatures(seriesForm.value.featuresText),
            sort_order: Number(seriesForm.value.sort_order || 0),
            is_published: Boolean(seriesForm.value.is_published),
        };
        if (editingSeries.value?.id) {
            await api.updateManagerBrandSeries(selectedBrandId.value, editingSeries.value.id, payload);
        } else {
            await api.createManagerBrandSeries(selectedBrandId.value, payload);
        }
        await fetchSeries();
        closeSeriesModal();
        setToast(wasEditing ? 'Серия обновлена' : 'Серия создана');
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    } finally {
        seriesSaving.value = false;
    }
};

const deleteSeries = async (series: ManagerBrandSeries) => {
    if (!selectedBrandId.value) return;
    if (!confirm(`Удалить серию "${series.title}"?`)) return;

    seriesError.value = '';
    try {
        await api.deleteManagerBrandSeries(selectedBrandId.value, series.id);
        await fetchSeries();
        setToast('Серия удалена');
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    }
};

watch(selectedBrandId, () => {
    fetchSeries();
});

onMounted(() => {
    fetchBrands();
});
</script>

<template>
    <div class="space-y-5">
        <Transition name="fade">
            <div v-if="toast" class="fixed top-6 right-6 z-[100] rounded-xl bg-teal-600 px-6 py-3 font-medium text-white shadow-2xl">
                {{ toast }}
            </div>
        </Transition>

        <div class="flex items-center justify-between">
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">Бренды</h1>
            <button
                type="button"
                class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 transition-all"
                @click="openCreate"
            >
                <span class="material-icons-round text-[18px]">add</span>
                Новый бренд
            </button>
        </div>

        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/70 p-4 space-y-4">
            <div class="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
                <input
                    v-model="query"
                    type="text"
                    placeholder="Поиск по названию или slug"
                    class="w-full sm:max-w-sm px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg text-sm"
                />
                <div class="text-xs text-gray-500 dark:text-slate-400">
                    Всего: {{ filteredBrands.length }}
                </div>
            </div>

            <div v-if="error" class="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                {{ error }}
            </div>

            <div v-if="loading" class="py-6 text-sm text-gray-500 dark:text-slate-400">Загрузка брендов...</div>
            <div v-else-if="filteredBrands.length === 0" class="py-6 text-sm text-gray-500 dark:text-slate-400">Бренды не найдены.</div>

            <div v-else class="overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="text-left text-gray-500 dark:text-slate-400 border-b border-gray-100 dark:border-slate-700">
                            <th class="py-2 pr-3 font-semibold">Бренд</th>
                            <th class="py-2 pr-3 font-semibold">Slug</th>
                            <th class="py-2 pr-3 font-semibold">Товаров</th>
                            <th class="py-2 pr-3 font-semibold">Порядок</th>
                            <th class="py-2 pr-3 font-semibold">Статус</th>
                            <th class="py-2 text-right font-semibold">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="brand in filteredBrands"
                            :key="brand.id"
                            class="border-b border-gray-100 dark:border-slate-800/80 cursor-pointer transition-colors"
                            :class="selectedBrandId === brand.id ? 'bg-teal-50/80 dark:bg-teal-900/20' : 'hover:bg-gray-50 dark:hover:bg-slate-800'"
                            @click="selectBrand(brand)"
                        >
                            <td class="py-2 pr-3">
                                <div class="flex items-center gap-2 min-w-[220px]">
                                    <img
                                        v-if="brand.logo_url"
                                        :src="brand.logo_url"
                                        :alt="brand.title"
                                        class="w-7 h-7 rounded bg-white object-contain border border-gray-200"
                                    />
                                    <div>
                                        <div class="font-semibold text-gray-800 dark:text-slate-200">{{ brand.title }}</div>
                                        <div v-if="brand.description" class="text-xs text-gray-500 dark:text-slate-400 truncate max-w-[360px]">
                                            {{ brand.description }}
                                        </div>
                                    </div>
                                </div>
                            </td>
                            <td class="py-2 pr-3 text-gray-600 dark:text-slate-300 font-mono">{{ brand.slug }}</td>
                            <td class="py-2 pr-3 text-gray-700 dark:text-slate-200">{{ brand.products_count }}</td>
                            <td class="py-2 pr-3 text-gray-700 dark:text-slate-200">{{ brand.sort_order }}</td>
                            <td class="py-2 pr-3">
                                <span
                                    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                                    :class="brand.is_published ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300'"
                                >
                                    {{ brand.is_published ? 'Публичный' : 'Скрыт' }}
                                </span>
                            </td>
                            <td class="py-2 text-right">
                                <div class="inline-flex items-center gap-1">
                                    <button
                                        type="button"
                                        class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-gray-50 dark:hover:bg-slate-700"
                                        @click.stop="selectBrand(brand)"
                                    >
                                        Серии
                                    </button>
                                    <button
                                        type="button"
                                        class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-gray-50 dark:hover:bg-slate-700"
                                        @click.stop="openEdit(brand)"
                                    >
                                        Изменить
                                    </button>
                                    <button
                                        type="button"
                                        class="px-2.5 py-1 rounded border border-red-200 text-red-600 text-xs font-semibold hover:bg-red-50 disabled:opacity-50"
                                        :disabled="(brand.products_count ?? 0) > 0"
                                        @click.stop="deleteBrand(brand)"
                                    >
                                        Удалить
                                    </button>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/70 p-4 space-y-4">
            <div class="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
                <div>
                    <p class="text-xs uppercase tracking-[0.18em] font-bold text-teal-600 dark:text-teal-300">Серии бренда</p>
                    <h2 class="text-lg font-bold text-gray-900 dark:text-white">
                        {{ selectedBrand ? selectedBrand.title : 'Выберите бренд' }}
                    </h2>
                    <p class="text-sm text-gray-500 dark:text-slate-400">
                        Описания и фичи попадут на брендовые страницы и в блок связанных моделей.
                    </p>
                </div>
                <button
                    type="button"
                    class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 transition-all disabled:opacity-50"
                    :disabled="!selectedBrand"
                    @click="openSeriesCreate"
                >
                    <span class="material-icons-round text-[18px]">add</span>
                    Новая серия
                </button>
            </div>

            <div v-if="seriesError" class="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                {{ seriesError }}
            </div>

            <div v-if="!selectedBrand" class="py-6 text-sm text-gray-500 dark:text-slate-400">
                Выберите бренд в таблице выше.
            </div>
            <div v-else-if="seriesLoading" class="py-6 text-sm text-gray-500 dark:text-slate-400">
                Загрузка серий...
            </div>
            <div v-else-if="seriesItems.length === 0" class="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 px-4 py-8 text-sm text-gray-500 dark:text-slate-400">
                У бренда пока нет серий. Можно добавить первую вручную.
            </div>
            <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <article
                    v-for="series in seriesItems"
                    :key="series.id"
                    class="rounded-xl border border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 p-4 space-y-3"
                >
                    <div class="flex items-start gap-3">
                        <img
                            v-if="series.hero_image"
                            :src="series.hero_image"
                            :alt="series.title"
                            class="w-16 h-16 rounded-lg object-cover border border-gray-200 dark:border-slate-700 bg-white"
                        />
                        <div class="min-w-0 flex-1">
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="font-bold text-gray-900 dark:text-slate-100">{{ series.title }}</h3>
                                <span
                                    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                                    :class="series.is_published ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300'"
                                >
                                    {{ series.is_published ? 'Публичная' : 'Скрыта' }}
                                </span>
                            </div>
                            <p class="text-xs font-mono text-gray-500 dark:text-slate-400">{{ series.slug }}</p>
                            <p v-if="series.description" class="mt-2 text-sm text-gray-600 dark:text-slate-300 line-clamp-3">
                                {{ series.description }}
                            </p>
                        </div>
                    </div>
                    <div v-if="series.features?.length" class="flex flex-wrap gap-2">
                        <span
                            v-for="feature in series.features"
                            :key="feature"
                            class="rounded-full border border-teal-200 dark:border-teal-900/60 bg-teal-50 dark:bg-teal-950/30 px-2.5 py-1 text-xs font-semibold text-teal-700 dark:text-teal-200"
                        >
                            {{ feature }}
                        </span>
                    </div>
                    <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500 dark:text-slate-400">
                        <span>{{ series.products_count }} товаров · порядок {{ series.sort_order }}</span>
                        <div class="inline-flex items-center gap-1">
                            <button
                                type="button"
                                class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-white dark:hover:bg-slate-800"
                                @click="openSeriesEdit(series)"
                            >
                                Изменить
                            </button>
                            <button
                                type="button"
                                class="px-2.5 py-1 rounded border border-red-200 text-red-600 text-xs font-semibold hover:bg-red-50 disabled:opacity-50"
                                :disabled="(series.products_count ?? 0) > 0"
                                @click="deleteSeries(series)"
                            >
                                Удалить
                            </button>
                        </div>
                    </div>
                </article>
            </div>
        </div>

        <div
            v-if="modalOpen"
            class="fixed inset-0 z-[70] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
            @click.self="closeModal"
        >
            <div class="w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
                <header class="px-5 py-4 border-b border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">
                        {{ editingBrand ? 'Редактирование бренда' : 'Новый бренд' }}
                    </h2>
                </header>
                <div class="p-5 space-y-3">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label class="text-sm space-y-1">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Название</span>
                            <input v-model="form.title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                        <label class="text-sm space-y-1">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Slug</span>
                            <input v-model="form.slug" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                    </div>
                    <label class="text-sm space-y-1 block">
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Логотип (URL)</span>
                        <input v-model="form.logo_url" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                    </label>
                    <label class="text-sm space-y-1 block">
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Описание</span>
                        <textarea v-model="form.description" rows="4" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        <span class="block text-xs text-gray-500 dark:text-slate-400">
                            Можно использовать Markdown: абзацы, списки, ссылки, **жирный**, *курсив*.
                        </span>
                    </label>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label class="text-sm space-y-1 block">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Sort order</span>
                            <input v-model.number="form.sort_order" type="number" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                        <label class="text-sm flex items-center gap-2 pt-6">
                            <input v-model="form.is_published" type="checkbox" class="rounded border-gray-300 dark:border-slate-700" />
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Публиковать бренд</span>
                        </label>
                    </div>
                </div>
                <footer class="px-5 py-4 border-t border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-end gap-2">
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700" @click="closeModal">
                        Отмена
                    </button>
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50" :disabled="saving" @click="saveBrand">
                        {{ saving ? 'Сохранение...' : 'Сохранить' }}
                    </button>
                </footer>
            </div>
        </div>

        <div
            v-if="seriesModalOpen"
            class="fixed inset-0 z-[70] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
            @click.self="closeSeriesModal"
        >
            <div class="w-full max-w-3xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
                <header class="px-5 py-4 border-b border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">
                        {{ editingSeries ? 'Редактирование серии' : 'Новая серия' }}
                    </h2>
                    <p v-if="selectedBrand" class="text-sm text-gray-500 dark:text-slate-400">{{ selectedBrand.title }}</p>
                </header>
                <div class="p-5 space-y-3">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label class="text-sm space-y-1">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Название</span>
                            <input v-model="seriesForm.title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                        <label class="text-sm space-y-1">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Slug</span>
                            <input v-model="seriesForm.slug" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                    </div>
                    <label class="text-sm space-y-1 block">
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Hero image (URL)</span>
                        <input v-model="seriesForm.hero_image" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                    </label>
                    <label class="text-sm space-y-1 block">
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Описание серии</span>
                        <textarea v-model="seriesForm.description" rows="5" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        <span class="block text-xs text-gray-500 dark:text-slate-400">
                            Короткий текст для страницы бренда и карточки товара.
                        </span>
                    </label>
                    <label class="text-sm space-y-1 block">
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Фичи серии</span>
                        <textarea v-model="seriesForm.featuresText" rows="5" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="Одна фича на строку" />
                    </label>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label class="text-sm space-y-1 block">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Sort order</span>
                            <input v-model.number="seriesForm.sort_order" type="number" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                        <label class="text-sm flex items-center gap-2 pt-6">
                            <input v-model="seriesForm.is_published" type="checkbox" class="rounded border-gray-300 dark:border-slate-700" />
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Публиковать серию</span>
                        </label>
                    </div>
                </div>
                <footer class="px-5 py-4 border-t border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-end gap-2">
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700" @click="closeSeriesModal">
                        Отмена
                    </button>
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50" :disabled="seriesSaving" @click="saveSeries">
                        {{ seriesSaving ? 'Сохранение...' : 'Сохранить' }}
                    </button>
                </footer>
            </div>
        </div>
    </div>
</template>
