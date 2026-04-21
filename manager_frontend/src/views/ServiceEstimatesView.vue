<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api';
import type {
    ManagerInstallEstimateResponse,
    ManagerServiceEstimateResponse,
    ManagerTariffResponse,
    ServiceResponse,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

type SelectedAddon = {
    slug: string;
    title: string;
    qty: number;
    base_price: number;
};

const tariffs = ref<ManagerTariffResponse[]>([]);
const loadingTariffs = ref(false);
const error = ref('');
const toast = ref('');

const estimateForm = ref({
    tariff_id: null as number | null,
    route_length_m: 5,
    quantity: 1,
    extra_holes_count: 0,
    extra_hole_price: 35,
    discount_amount: 0,
});

const addonQuery = ref('');
const addonSearchLoading = ref(false);
const addonSearchResults = ref<ServiceResponse[]>([]);
const selectedAddons = ref<SelectedAddon[]>([]);

const calculating = ref(false);
const calculation = ref<ManagerInstallEstimateResponse | null>(null);

const saveForm = ref({
    title: '',
    comment: '',
    customer_id: '',
    status: 'draft',
});
const saving = ref(false);

const listLoading = ref(false);
const listPage = ref(1);
const listLimit = ref(20);
const listTotal = ref(0);
const estimates = ref<ManagerServiceEstimateResponse[]>([]);

const detailLoading = ref(false);
const selectedEstimate = ref<ManagerServiceEstimateResponse | null>(null);
const deletingEstimateId = ref<number | null>(null);

const selectedTariff = computed(
    () => tariffs.value.find((item) => item.id === estimateForm.value.tariff_id) ?? null
);

const totalPages = computed(() => Math.max(1, Math.ceil(listTotal.value / listLimit.value)));

const setToast = (message: string) => {
    toast.value = message;
    window.setTimeout(() => {
        toast.value = '';
    }, 3000);
};

const formatMoney = (value: number) =>
    new Intl.NumberFormat('ru-BY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value ?? 0);

const formatDateTime = (iso: string) =>
    new Date(iso).toLocaleString('ru-BY', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });

const statusBadgeClass = (status: string) => {
    const normalized = (status || '').toLowerCase();
    if (normalized === 'approved') return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    if (normalized === 'sent') return 'bg-blue-100 text-blue-700 border-blue-200';
    if (normalized === 'rejected') return 'bg-red-100 text-red-700 border-red-200';
    return 'bg-gray-100 text-gray-700 border-gray-200';
};

const loadTariffs = async () => {
    loadingTariffs.value = true;
    try {
        const response = await api.listManagerTariffs();
        tariffs.value = [...response.items].sort((a, b) => {
            const byCategory = a.category.localeCompare(b.category, 'ru');
            if (byCategory !== 0) return byCategory;
            return (a.power_range || '').localeCompare(b.power_range || '', 'ru');
        });
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        loadingTariffs.value = false;
    }
};

const loadEstimates = async (page = listPage.value) => {
    listLoading.value = true;
    try {
        const response = await api.listManagerServiceEstimates(page, listLimit.value);
        listPage.value = response.page;
        listLimit.value = response.limit;
        listTotal.value = response.total;
        estimates.value = response.items;
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        listLoading.value = false;
    }
};

const normalizeNumber = (value: number, min = 0) => {
    if (!Number.isFinite(value)) return min;
    return Math.max(min, value);
};

const searchAddons = async () => {
    const query = addonQuery.value.trim();
    if (query.length < 2) {
        addonSearchResults.value = [];
        return;
    }
    addonSearchLoading.value = true;
    try {
        const response = await api.searchServices(query);
        addonSearchResults.value = (response.items || []).filter((service: ServiceResponse) => service.is_active);
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        addonSearchLoading.value = false;
    }
};

const addAddon = (service: ServiceResponse) => {
    const existing = selectedAddons.value.find((item) => item.slug === service.slug);
    if (existing) {
        existing.qty += 1;
        return;
    }
    selectedAddons.value.push({
        slug: service.slug,
        title: service.title,
        qty: 1,
        base_price: service.base_price,
    });
};

const removeAddon = (slug: string) => {
    selectedAddons.value = selectedAddons.value.filter((item) => item.slug !== slug);
};

const buildPayload = () => ({
    tariff_id: estimateForm.value.tariff_id,
    route_length_m: normalizeNumber(estimateForm.value.route_length_m, 0),
    quantity: Math.max(1, Math.trunc(normalizeNumber(estimateForm.value.quantity, 1))),
    extra_holes_count: Math.max(0, Math.trunc(normalizeNumber(estimateForm.value.extra_holes_count, 0))),
    extra_hole_price: normalizeNumber(estimateForm.value.extra_hole_price, 0),
    discount_amount: normalizeNumber(estimateForm.value.discount_amount, 0),
    addons: selectedAddons.value
        .filter((item) => item.qty > 0)
        .map((item) => ({ slug: item.slug, qty: Math.max(1, Math.trunc(item.qty)) })),
});

const calculateEstimate = async () => {
    if (!estimateForm.value.tariff_id) {
        error.value = 'Выберите тариф для расчета сметы.';
        return;
    }
    calculating.value = true;
    error.value = '';
    try {
        calculation.value = await api.calculateManagerInstallEstimate(buildPayload());
    } catch (e) {
        calculation.value = null;
        error.value = getApiErrorMessage(e);
    } finally {
        calculating.value = false;
    }
};

const openEstimate = async (estimateId: number) => {
    detailLoading.value = true;
    try {
        selectedEstimate.value = await api.getManagerServiceEstimate(estimateId);
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        detailLoading.value = false;
    }
};

const saveEstimate = async () => {
    if (!calculation.value) {
        await calculateEstimate();
        if (!calculation.value) return;
    }

    saving.value = true;
    error.value = '';
    try {
        const normalizedCustomerId = Number.parseInt(saveForm.value.customer_id, 10);
        const response = await api.createManagerServiceEstimate({
            ...buildPayload(),
            title: saveForm.value.title.trim() || null,
            comment: saveForm.value.comment.trim() || null,
            customer_id: Number.isFinite(normalizedCustomerId) ? normalizedCustomerId : null,
            status: saveForm.value.status.trim() || 'draft',
        });
        setToast(`Смета #${response.id} сохранена`);
        await loadEstimates(1);
        await openEstimate(response.id);
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        saving.value = false;
    }
};

const deleteEstimate = async (estimate: ManagerServiceEstimateResponse) => {
    const ok = window.confirm(`Удалить смету #${estimate.id}? Это действие нельзя отменить.`);
    if (!ok) return;

    deletingEstimateId.value = estimate.id;
    error.value = '';
    try {
        await api.deleteManagerServiceEstimate(estimate.id);
        if (selectedEstimate.value?.id === estimate.id) {
            selectedEstimate.value = null;
        }
        setToast(`Смета #${estimate.id} удалена`);
        await loadEstimates(listPage.value);
    } catch (e) {
        error.value = getApiErrorMessage(e);
    } finally {
        deletingEstimateId.value = null;
    }
};

const resetForm = () => {
    estimateForm.value = {
        tariff_id: null,
        route_length_m: 5,
        quantity: 1,
        extra_holes_count: 0,
        extra_hole_price: 35,
        discount_amount: 0,
    };
    selectedAddons.value = [];
    calculation.value = null;
    addonQuery.value = '';
    addonSearchResults.value = [];
};

onMounted(async () => {
    await Promise.all([loadTariffs(), loadEstimates(1)]);
});
</script>

<template>
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
        <Transition name="toast">
            <div
                v-if="toast"
                class="fixed top-20 right-8 z-50 bg-teal-600 border border-teal-500 text-white px-4 py-3 rounded-lg shadow-xl shadow-teal-900/30 flex items-center gap-3"
            >
                <span class="material-icons-round text-xl">check_circle</span>
                <span class="text-sm font-medium">{{ toast }}</span>
            </div>
        </Transition>

        <div class="flex flex-col gap-2 mb-8">
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
                <span class="material-icons-round text-teal-600 dark:text-teal-400">request_quote</span>
                Сметы монтажа
            </h1>
            <p class="text-sm text-gray-500 dark:text-slate-400">
                Быстрый расчет монтажной сметы с сохранением снапшота для менеджера
            </p>
        </div>

        <div
            v-if="error"
            class="mb-6 rounded-xl border border-red-200 dark:border-red-500/50 bg-red-50 dark:bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400"
        >
            {{ error }}
        </div>

        <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <section class="bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/60 p-5">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Параметры расчета</h2>
                    <button
                        class="text-xs font-medium text-gray-500 hover:text-gray-800 dark:text-slate-400 dark:hover:text-slate-200"
                        @click="resetForm"
                    >
                        Сбросить
                    </button>
                </div>

                <div class="space-y-4">
                    <label class="block">
                        <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Тариф</span>
                        <select
                            v-model.number="estimateForm.tariff_id"
                            class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-gray-900 dark:text-slate-100"
                            :disabled="loadingTariffs"
                        >
                            <option :value="null">Выберите тариф</option>
                            <option v-for="tariff in tariffs" :key="tariff.id" :value="tariff.id">
                                {{ tariff.category }} · {{ tariff.power_range || 'all' }} · {{ tariff.base_price }} BYN
                            </option>
                        </select>
                    </label>
                    <p v-if="selectedTariff" class="text-xs text-gray-500 dark:text-slate-400">
                        В тариф включено {{ selectedTariff.included_pipe_meters }} м трассы, доп. метр:
                        {{ selectedTariff.extra_pipe_price }} BYN.
                    </p>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <label class="block">
                            <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Длина трассы (м)</span>
                            <input
                                v-model.number="estimateForm.route_length_m"
                                type="number"
                                min="0"
                                step="0.5"
                                class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            />
                        </label>
                        <label class="block">
                            <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Количество комплектов</span>
                            <input
                                v-model.number="estimateForm.quantity"
                                type="number"
                                min="1"
                                step="1"
                                class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            />
                        </label>
                        <label class="block">
                            <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Доп. отверстий (шт)</span>
                            <input
                                v-model.number="estimateForm.extra_holes_count"
                                type="number"
                                min="0"
                                step="1"
                                class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            />
                        </label>
                        <label class="block">
                            <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Цена отверстия (BYN)</span>
                            <input
                                v-model.number="estimateForm.extra_hole_price"
                                type="number"
                                min="0"
                                step="0.01"
                                class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            />
                        </label>
                    </div>

                    <label class="block">
                        <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Скидка (BYN)</span>
                        <input
                            v-model.number="estimateForm.discount_amount"
                            type="number"
                            min="0"
                            step="0.01"
                            class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                        />
                    </label>

                    <div class="pt-2 border-t border-gray-200 dark:border-slate-700">
                        <div class="flex items-center justify-between mb-2">
                            <h3 class="text-sm font-semibold text-gray-800 dark:text-slate-100">Дополнительные работы</h3>
                            <span class="text-xs text-gray-500 dark:text-slate-400">по slug из services</span>
                        </div>
                        <div class="flex flex-col sm:flex-row gap-2 mb-2">
                            <input
                                v-model="addonQuery"
                                type="text"
                                placeholder="Поиск услуг (например, pump)"
                                class="flex-1 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            />
                            <button
                                class="inline-flex items-center justify-center gap-1 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm font-medium hover:bg-gray-50 dark:hover:bg-slate-700"
                                :disabled="addonSearchLoading"
                                @click="searchAddons"
                            >
                                <span class="material-icons-round text-[18px]">search</span>
                                {{ addonSearchLoading ? 'Ищу...' : 'Найти' }}
                            </button>
                        </div>

                        <div v-if="addonSearchResults.length" class="mb-3 rounded-lg border border-gray-200 dark:border-slate-700 overflow-hidden">
                            <div
                                v-for="service in addonSearchResults"
                                :key="service.id"
                                class="flex items-center justify-between gap-3 px-3 py-2 text-sm bg-white dark:bg-slate-800 border-b border-gray-100 dark:border-slate-700 last:border-b-0"
                            >
                                <div class="min-w-0">
                                    <div class="font-medium text-gray-900 dark:text-slate-100 truncate">{{ service.title }}</div>
                                    <div class="text-xs text-gray-500 dark:text-slate-400">{{ service.slug }} · {{ service.base_price }} BYN</div>
                                </div>
                                <button
                                    class="shrink-0 rounded-md border border-teal-300 text-teal-700 dark:text-teal-400 px-2 py-1 text-xs font-medium hover:bg-teal-50 dark:hover:bg-teal-500/10"
                                    @click="addAddon(service)"
                                >
                                    Добавить
                                </button>
                            </div>
                        </div>

                        <div v-if="selectedAddons.length" class="space-y-2">
                            <div
                                v-for="addon in selectedAddons"
                                :key="addon.slug"
                                class="grid grid-cols-[1fr_auto_auto] gap-2 items-center rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/70 px-3 py-2"
                            >
                                <div>
                                    <div class="text-sm font-medium text-gray-900 dark:text-slate-100">{{ addon.title }}</div>
                                    <div class="text-xs text-gray-500 dark:text-slate-400">{{ addon.slug }} · {{ addon.base_price }} BYN</div>
                                </div>
                                <input
                                    v-model.number="addon.qty"
                                    type="number"
                                    min="1"
                                    step="1"
                                    class="w-20 rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-2 py-1 text-sm"
                                />
                                <button
                                    class="inline-flex items-center justify-center rounded-md border border-red-200 text-red-600 hover:bg-red-50 px-2 py-1"
                                    @click="removeAddon(addon.slug)"
                                    title="Удалить"
                                >
                                    <span class="material-icons-round text-[16px]">delete</span>
                                </button>
                            </div>
                        </div>
                        <p v-else class="text-xs text-gray-500 dark:text-slate-400">Допработы не выбраны</p>
                    </div>

                    <button
                        class="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white py-2.5 font-medium"
                        :disabled="calculating"
                        @click="calculateEstimate"
                    >
                        <span class="material-icons-round text-[18px]">calculate</span>
                        {{ calculating ? 'Расчет...' : 'Рассчитать смету' }}
                    </button>
                </div>
            </section>

            <section class="bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/60 p-5">
                <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Результат расчета</h2>

                <div v-if="calculation" class="space-y-4">
                    <div class="flex flex-wrap gap-2">
                        <span class="inline-flex items-center rounded-full border border-gray-200 dark:border-slate-600 px-3 py-1 text-xs text-gray-600 dark:text-slate-300">
                            {{ calculation.category }}
                        </span>
                        <span class="inline-flex items-center rounded-full border border-gray-200 dark:border-slate-600 px-3 py-1 text-xs text-gray-600 dark:text-slate-300">
                            {{ calculation.power_range || 'all' }}
                        </span>
                        <span class="inline-flex items-center rounded-full border border-gray-200 dark:border-slate-600 px-3 py-1 text-xs text-gray-600 dark:text-slate-300">
                            Включено трассы: {{ calculation.included_pipe_meters }} м
                        </span>
                        <span class="inline-flex items-center rounded-full border border-gray-200 dark:border-slate-600 px-3 py-1 text-xs text-gray-600 dark:text-slate-300">
                            Доп. трасса: {{ calculation.extra_pipe_meters }} м
                        </span>
                    </div>

                    <div class="rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden">
                        <table class="min-w-full divide-y divide-gray-200 dark:divide-slate-700 text-sm">
                            <thead class="bg-gray-50 dark:bg-slate-800/80">
                                <tr>
                                    <th class="text-left px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Позиция</th>
                                    <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Кол-во</th>
                                    <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Цена</th>
                                    <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Сумма</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-100 dark:divide-slate-700 bg-white dark:bg-[#1e293b]">
                                <tr v-for="line in calculation.lines" :key="`${line.source_type}-${line.sort_order}-${line.name}`">
                                    <td class="px-3 py-2 text-gray-900 dark:text-slate-100">{{ line.name }}</td>
                                    <td class="px-3 py-2 text-right text-gray-600 dark:text-slate-300">{{ line.qty }} {{ line.unit }}</td>
                                    <td class="px-3 py-2 text-right text-gray-600 dark:text-slate-300">{{ formatMoney(line.unit_price) }}</td>
                                    <td class="px-3 py-2 text-right font-semibold text-gray-900 dark:text-slate-100">{{ formatMoney(line.line_total) }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <div class="space-y-1 text-sm">
                        <div class="flex justify-between text-gray-600 dark:text-slate-300">
                            <span>Подытог</span>
                            <span>{{ formatMoney(calculation.subtotal) }} BYN</span>
                        </div>
                        <div class="flex justify-between text-gray-600 dark:text-slate-300">
                            <span>Скидка</span>
                            <span>- {{ formatMoney(calculation.discount_amount) }} BYN</span>
                        </div>
                        <div class="flex justify-between text-base font-semibold text-gray-900 dark:text-white pt-1 border-t border-gray-200 dark:border-slate-700">
                            <span>Итого</span>
                            <span>{{ formatMoney(calculation.total) }} BYN</span>
                        </div>
                    </div>

                    <div class="pt-4 border-t border-gray-200 dark:border-slate-700 space-y-3">
                        <h3 class="text-sm font-semibold text-gray-800 dark:text-slate-100">Сохранение сметы</h3>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <label class="block">
                                <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Название</span>
                                <input
                                    v-model="saveForm.title"
                                    type="text"
                                    placeholder="Смета для клиента"
                                    class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                                />
                            </label>
                            <label class="block">
                                <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">ID клиента (опц.)</span>
                                <input
                                    v-model="saveForm.customer_id"
                                    type="number"
                                    min="1"
                                    placeholder="123"
                                    class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                                />
                            </label>
                        </div>

                        <label class="block">
                            <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Статус</span>
                            <select
                                v-model="saveForm.status"
                                class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            >
                                <option value="draft">draft</option>
                                <option value="sent">sent</option>
                                <option value="approved">approved</option>
                                <option value="rejected">rejected</option>
                            </select>
                        </label>

                        <label class="block">
                            <span class="mb-1 block text-sm text-gray-600 dark:text-slate-300">Комментарий</span>
                            <textarea
                                v-model="saveForm.comment"
                                rows="3"
                                placeholder="Опционально: условия, примечания"
                                class="w-full rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                            />
                        </label>

                        <button
                            class="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white py-2.5 font-medium disabled:opacity-60 disabled:cursor-not-allowed"
                            :disabled="saving"
                            @click="saveEstimate"
                        >
                            <span class="material-icons-round text-[18px]">save</span>
                            {{ saving ? 'Сохраняю...' : 'Сохранить смету' }}
                        </button>
                    </div>
                </div>

                <div
                    v-else
                    class="h-full min-h-[240px] rounded-xl border border-dashed border-gray-300 dark:border-slate-600 flex items-center justify-center text-sm text-gray-500 dark:text-slate-400"
                >
                    Выберите параметры и нажмите «Рассчитать смету»
                </div>
            </section>
        </div>

        <section class="mt-6 bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/60 p-5">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Сохраненные сметы</h2>
                <button
                    class="inline-flex items-center gap-1 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm font-medium hover:bg-gray-50 dark:hover:bg-slate-700"
                    :disabled="listLoading"
                    @click="loadEstimates(listPage)"
                >
                    <span class="material-icons-round text-[18px]">refresh</span>
                    Обновить
                </button>
            </div>

            <div class="rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden">
                <table class="min-w-full divide-y divide-gray-200 dark:divide-slate-700 text-sm">
                    <thead class="bg-gray-50 dark:bg-slate-800/80">
                        <tr>
                            <th class="text-left px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">ID</th>
                            <th class="text-left px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Название</th>
                            <th class="text-left px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase hidden md:table-cell">Клиент</th>
                            <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Сумма</th>
                            <th class="text-center px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Статус</th>
                            <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase hidden lg:table-cell">Создано</th>
                            <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Действие</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 dark:divide-slate-700 bg-white dark:bg-[#1e293b]">
                        <tr v-for="item in estimates" :key="item.id" class="hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors">
                            <td class="px-3 py-2 font-medium text-gray-900 dark:text-slate-100">#{{ item.id }}</td>
                            <td class="px-3 py-2">
                                <div class="font-medium text-gray-900 dark:text-slate-100">{{ item.title }}</div>
                                <div class="text-xs text-gray-500 dark:text-slate-400">{{ item.service_kind }}</div>
                            </td>
                            <td class="px-3 py-2 text-gray-600 dark:text-slate-300 hidden md:table-cell">
                                {{ item.customer_id ? `#${item.customer_id}` : '—' }}
                            </td>
                            <td class="px-3 py-2 text-right font-semibold text-gray-900 dark:text-slate-100">
                                {{ formatMoney(item.total) }} {{ item.currency }}
                            </td>
                            <td class="px-3 py-2 text-center">
                                <span
                                    class="inline-flex rounded-full border px-2 py-0.5 text-xs font-medium"
                                    :class="statusBadgeClass(item.status)"
                                >
                                    {{ item.status }}
                                </span>
                            </td>
                            <td class="px-3 py-2 text-right text-gray-500 dark:text-slate-400 hidden lg:table-cell">
                                {{ formatDateTime(item.created_at) }}
                            </td>
                            <td class="px-3 py-2 text-right">
                                <div class="inline-flex items-center gap-2">
                                    <button
                                        class="inline-flex items-center gap-1 rounded-md border border-gray-300 dark:border-slate-600 px-2.5 py-1 text-xs font-medium hover:bg-gray-100 dark:hover:bg-slate-700"
                                        :disabled="detailLoading"
                                        @click="openEstimate(item.id)"
                                    >
                                        Открыть
                                    </button>
                                    <button
                                        class="inline-flex items-center gap-1 rounded-md border border-red-300 text-red-700 dark:text-red-300 px-2.5 py-1 text-xs font-medium hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-60 disabled:cursor-not-allowed"
                                        :disabled="deletingEstimateId === item.id"
                                        @click="deleteEstimate(item)"
                                    >
                                        {{ deletingEstimateId === item.id ? '...' : 'Удалить' }}
                                    </button>
                                </div>
                            </td>
                        </tr>
                        <tr v-if="!estimates.length && !listLoading">
                            <td colspan="7" class="px-3 py-10 text-center text-sm text-gray-500 dark:text-slate-400">
                                Пока нет сохраненных смет
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="mt-3 flex items-center justify-between text-sm">
                <div class="text-gray-500 dark:text-slate-400">
                    Всего: {{ listTotal }} · Страница {{ listPage }} из {{ totalPages }}
                </div>
                <div class="flex items-center gap-2">
                    <button
                        class="rounded-md border border-gray-300 dark:border-slate-600 px-3 py-1.5 disabled:opacity-50"
                        :disabled="listPage <= 1 || listLoading"
                        @click="loadEstimates(listPage - 1)"
                    >
                        Назад
                    </button>
                    <button
                        class="rounded-md border border-gray-300 dark:border-slate-600 px-3 py-1.5 disabled:opacity-50"
                        :disabled="listPage >= totalPages || listLoading"
                        @click="loadEstimates(listPage + 1)"
                    >
                        Вперёд
                    </button>
                </div>
            </div>
        </section>

        <section
            v-if="selectedEstimate"
            class="mt-6 bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/60 p-5"
        >
            <div class="flex items-start justify-between gap-3 mb-4">
                <div>
                    <h2 class="text-lg font-semibold text-gray-900 dark:text-white">
                        Детали сметы #{{ selectedEstimate.id }}
                    </h2>
                    <p class="text-sm text-gray-500 dark:text-slate-400">
                        {{ selectedEstimate.title }} · {{ formatDateTime(selectedEstimate.created_at) }}
                    </p>
                </div>
                <span class="inline-flex rounded-full border px-2.5 py-1 text-xs font-medium" :class="statusBadgeClass(selectedEstimate.status)">
                    {{ selectedEstimate.status }}
                </span>
            </div>

            <p v-if="selectedEstimate.comment" class="mb-4 text-sm text-gray-600 dark:text-slate-300">
                {{ selectedEstimate.comment }}
            </p>

            <div class="rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden">
                <table class="min-w-full divide-y divide-gray-200 dark:divide-slate-700 text-sm">
                    <thead class="bg-gray-50 dark:bg-slate-800/80">
                        <tr>
                            <th class="text-left px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Позиция</th>
                            <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Кол-во</th>
                            <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Цена</th>
                            <th class="text-right px-3 py-2 text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Сумма</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100 dark:divide-slate-700 bg-white dark:bg-[#1e293b]">
                        <tr v-for="line in (selectedEstimate.lines || [])" :key="`${line.source_type}-${line.sort_order}-${line.name}`">
                            <td class="px-3 py-2 text-gray-900 dark:text-slate-100">{{ line.name }}</td>
                            <td class="px-3 py-2 text-right text-gray-600 dark:text-slate-300">{{ line.qty }} {{ line.unit }}</td>
                            <td class="px-3 py-2 text-right text-gray-600 dark:text-slate-300">{{ formatMoney(line.unit_price) }}</td>
                            <td class="px-3 py-2 text-right font-semibold text-gray-900 dark:text-slate-100">{{ formatMoney(line.line_total) }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="mt-4 space-y-1 text-sm">
                <div class="flex justify-between text-gray-600 dark:text-slate-300">
                    <span>Подытог</span>
                    <span>{{ formatMoney(selectedEstimate.subtotal) }} {{ selectedEstimate.currency }}</span>
                </div>
                <div class="flex justify-between text-gray-600 dark:text-slate-300">
                    <span>Скидка</span>
                    <span>- {{ formatMoney(selectedEstimate.discount_amount) }} {{ selectedEstimate.currency }}</span>
                </div>
                <div class="flex justify-between text-base font-semibold text-gray-900 dark:text-white pt-1 border-t border-gray-200 dark:border-slate-700">
                    <span>Итого</span>
                    <span>{{ formatMoney(selectedEstimate.total) }} {{ selectedEstimate.currency }}</span>
                </div>
            </div>

            <details v-if="selectedEstimate.calculation_payload" class="mt-4 rounded-lg border border-gray-200 dark:border-slate-700 p-3">
                <summary class="cursor-pointer text-sm font-medium text-gray-700 dark:text-slate-300">
                    Исходный payload расчета
                </summary>
                <pre class="mt-2 overflow-auto text-xs text-gray-600 dark:text-slate-300">{{ JSON.stringify(selectedEstimate.calculation_payload, null, 2) }}</pre>
            </details>
        </section>
    </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toast-enter-from,
.toast-leave-to {
    opacity: 0;
    transform: translateY(-1rem) translateX(2rem);
}
</style>
