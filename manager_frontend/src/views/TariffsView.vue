<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api';
import type {
  ManagerTariffResponse,
  ManagerTariffRuleResponse,
  ManagerTariffServiceKind,
  InstallationLegacyCandidate,
  InstallationLegacyComparisonRow,
  InstallationLegacyComparisonResponse,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';
import TariffEditModal from '../components/TariffEditModal.vue';
import TariffRuleEditModal from '../components/TariffRuleEditModal.vue';
import { confirmDialog } from '../services/ui-feedback';

const tariffs = ref<ManagerTariffResponse[]>([]);
const loading = ref(false);
const error = ref('');
const toast = ref('');
const comparison = ref<InstallationLegacyComparisonResponse | null>(null);
const comparisonOffset = ref(0);
const comparisonLoading = ref(false);
const comparisonError = ref('');
const draftRefreshLoading = ref(false);
let comparisonRequestId = 0;
let tariffRequestId = 0;
let draftRefreshId = 0;
const publishing = ref(false);
const publishError = ref('');
const publishErrors: Record<string, string> = {
  empty_price_book: 'Нет активных тарифов с типизированным подбором.',
  invalid_matcher: 'Проверьте границы мощности, пару труб и условия веса.',
  missing_tariff_code: 'Для подбора монтажа нужен новый внутренний код. Откройте и сохраните тариф.',
  invalid_price_mode: 'Выберите режим цены: фиксированная, «от» или по запросу.',
  invalid_base_price: 'Проверьте базовую цену тарифа.',
  invalid_included_route: 'Включённая длина трассы должна быть неотрицательной.',
  invalid_included_holes: 'Количество включённых отверстий должно быть целым неотрицательным.',
  incomplete_fixed_matcher: 'Для фиксированной цены или цены «от» укажите границу мощности и обе трубы пары.',
  missing_base_price: 'Для фиксированной цены или цены «от» нужна положительная базовая цена.',
  missing_route_price: 'Добавьте правило «Трасса сверх включённой» с ценой.',
  missing_hole_price: 'Для включённых отверстий добавьте цену отверстия сверх включённого.',
  missing_component_code: 'У активного правила не указан смысл компонента.',
  matcher_conflict: 'Два тарифа пересекаются по условиям подбора с одинаковой точностью.',
  duplicate_component_code: 'В одном тарифе два правила с одинаковым смыслом.',
  site_extra_conflict: 'Цена общих работ на объекте различается между тарифами.',
  invalid_component_rule: 'Тип расчёта или единица правила не совпадает с выбранным компонентом.',
  component_code_conflict: 'Один компонент имеет разные единицы или способы расчёта в тарифах.',
  unknown_component_code: 'Выберите поддерживаемый смысл компонента для правила.',
  invalid_rule_price: 'Проверьте цену правила.',
  extra_default_on: 'Дополнительная работа должна быть выключена по умолчанию.',
  invalid_discount_rule: 'Проверьте способ расчёта скидки комплекта.',
  excessive_discount: 'Скидка комплекта превышает базовую цену.',
  tariff_code_reused: 'Условия уже опубликованного тарифа изменены. Откройте тариф и выберите «Новые условия подбора».',
  component_code_reused: 'Смысл опубликованного компонента нельзя менять. Выберите другой компонент.',
  duplicate_tariff_code: 'Два активных тарифа имеют один код установки.',
  packed_weight_requires_transport_rule: 'Для подбора монтажа используйте вес блока без упаковки.',
};
const invalidateComparison = () => {
  comparisonRequestId += 1;
  comparison.value = null;
  comparisonLoading.value = false;
  comparisonError.value = '';
};
const loadComparison = async () => {
  const requestId = ++comparisonRequestId;
  const offset = comparisonOffset.value;
  comparisonLoading.value = true;
  comparisonError.value = '';
  comparison.value = null;
  try {
    const response = await api.listManagerInstallationLegacyComparison(offset);
    if (requestId === comparisonRequestId) comparison.value = response;
  } catch (e) {
    if (requestId === comparisonRequestId) comparisonError.value = getApiErrorMessage(e);
  } finally {
    if (requestId === comparisonRequestId) comparisonLoading.value = false;
  }
};
const comparisonStatus = computed(() => {
  if (comparisonLoading.value || draftRefreshLoading.value) return 'проверяем статус публикации…';
  if (comparisonError.value || !comparison.value) return 'статус публикации недоступен';
  return comparison.value.price_book_revision
    ? `ревизия ${comparison.value.price_book_revision} опубликована`
    : 'ещё не опубликована';
});
const comparisonReady = computed(() => !comparisonLoading.value && !draftRefreshLoading.value && !comparisonError.value && comparison.value !== null);
const publicationTarget = (message: string): string => {
  const tariffIds = [...message.matchAll(/Tariff (\d+)/g)].map((match) => Number(match[1]));
  const ruleIds = [...message.matchAll(/Rule (\d+)/g)].map((match) => Number(match[1]));
  const names = tariffs.value.filter((tariff) =>
    tariffIds.includes(tariff.id) ||
    (tariff.installation_code && message.includes(tariff.installation_code)) ||
    tariff.rules?.some((rule) => ruleIds.includes(rule.id))
  ).map((tariff) => tariffShortName(tariff));
  return names.length ? ` Проверьте ${names.length === 1 ? 'тариф' : 'тарифы'}: ${names.join(', ')}.` : '';
};
const publish = async () => {
  if (publishing.value || !comparisonReady.value || loading.value || error.value) return;
  if (!await confirmDialog({ title: 'Опубликовать книгу монтажа?', description: 'Активные тарифы с типизированным подбором станут новой неизменяемой ревизией. Старые публичные расценки не копируются и не меняются.', confirmText: 'Опубликовать' })) return;
  if (!comparisonReady.value || kindFilter.value !== 'installation' || loading.value || error.value) return;
  publishing.value = true;
  publishError.value = '';
  try {
    const result = await api.publishManagerInstallationPriceBook();
    setToast(`Опубликована ревизия ${result.revision}`);
    await loadComparison();
  } catch (e) {
    const detail = (e as { body?: { detail?: { code?: string; message?: string } } })?.body?.detail;
    publishError.value = (e as { status?: number })?.status === 403
      ? 'Нет прав на публикацию книги монтажа.'
      : detail?.code && publishErrors[detail.code]
        ? `${publishErrors[detail.code]}${publicationTarget(detail.message ?? '')}`
        : `Не удалось опубликовать книгу: ${getApiErrorMessage(e)}`;
  } finally { publishing.value = false; }
};

const kindFilter = ref<ManagerTariffServiceKind>('installation');
const includeInactive = ref(true);

const showTariffModal = ref(false);
const editingTariff = ref<ManagerTariffResponse | null>(null);

const showRuleModal = ref(false);
const editingRule = ref<ManagerTariffRuleResponse | null>(null);
const selectedTariffId = ref<number | null>(null);

const selectedTariff = computed(
  () => tariffs.value.find((item) => item.id === selectedTariffId.value) ?? null
);

const serviceKindOptions: Array<{ value: ManagerTariffServiceKind; label: string }> = [
  { value: 'installation', label: 'Монтаж' },
  { value: 'pre_install', label: 'Закладка коммуникаций' },
  { value: 'dismantling', label: 'Демонтаж' },
  { value: 'maintenance', label: 'Обслуживание' },
  { value: 'repair', label: 'Ремонт' },
];

const serviceKindLabel = (kind: ManagerTariffServiceKind | string) =>
  serviceKindOptions.find((item) => item.value === kind)?.label ?? String(kind || 'Услуга');
const indoorTypesLabel = (kind: string) => ({ wall: 'настенный', cassette: 'кассетный', duct: 'канальный', floor_ceiling: 'напольно-потолочный', column: 'колонный', console: 'консольный' }[kind] ?? kind);
const tariffShortName = (tariff: ManagerTariffResponse) => tariff.short_name || tariff.selector_label;
const tariffFullDescription = (tariff: ManagerTariffResponse) => tariff.full_description || tariffShortName(tariff);
const candidateName = (candidate: InstallationLegacyCandidate) => {
  const tariff = tariffs.value.find((item) => item.installation_code === candidate.tariff_code);
  return tariff ? tariffShortName(tariff) : 'Тариф черновика';
};
const money = (value: number | string) => Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
const matcherSummary = (candidate: InstallationLegacyCandidate) => {
  const match = candidate.matcher;
  const capacity = match.capacity_min_kw != null && match.capacity_max_kw != null
    ? `${match.capacity_min_kw}–${match.capacity_max_kw} кВт`
    : match.capacity_min_kw != null ? `от ${match.capacity_min_kw} кВт`
      : match.capacity_max_kw != null ? `до ${match.capacity_max_kw} кВт` : 'мощность не задана';
  const pipes = match.pipe_liquid && match.pipe_gas
    ? `трубы ${match.pipe_liquid} + ${match.pipe_gas}` : 'пара труб не задана';
  const weightKind = match.weight_source === 'weight_indoor' ? 'внутреннего блока'
    : match.weight_source === 'weight_outdoor' ? 'наружного блока' : 'блока в упаковке';
  const weight = match.weight_source
    ? ` · вес ${weightKind} ${match.weight_min_kg ?? '0'}–${match.weight_max_kg ?? '∞'} кг` : '';
  return `${match.product_kind === 'multi_split_system' ? 'Мультисплит' : indoorTypesLabel(match.indoor_type || '')} · ${capacity} · ${pipes}${weight}`;
};
const candidatePrice = (candidate: InstallationLegacyCandidate) =>
  `${candidate.mode === 'quote' ? 'По запросу · черновая база' : candidate.mode === 'from' ? 'База от' : 'База'} ${money(candidate.base_price)} BYN · доп. трасса ${candidate.route_extra_price == null ? 'не задана' : `${money(candidate.route_extra_price)} BYN/м`}`;
const candidatePriceReview = (row: InstallationLegacyComparisonRow, candidate: InstallationLegacyCandidate) => {
  if (candidate.mode === 'quote') return 'Цена по запросу: числовое сравнение не применяется';
  if (candidate.mode === 'from') return 'Цена «от» — нижняя граница, не точное совпадение';
  const differences = [
    Number(row.legacy_base_price) !== Number(candidate.base_price) ? 'база' : null,
    candidate.route_extra_price == null || Number(row.legacy_route_extra_price) !== Number(candidate.route_extra_price) ? 'доп. трасса' : null,
  ].filter(Boolean);
  return differences.length ? `Различаются: ${differences.join(', ')}` : 'База и доп. трасса совпадают; подбор проверить';
};

const ROUTE_AWARE_SERVICE_KINDS = new Set<ManagerTariffServiceKind>(['installation', 'pre_install']);
const shouldShowRouteColumn = computed(() => ROUTE_AWARE_SERVICE_KINDS.has(kindFilter.value));

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};

const loadTariffs = async () => {
  const requestId = ++tariffRequestId;
  const kind = kindFilter.value;
  const inactive = includeInactive.value;
  loading.value = true;
  error.value = '';
  try {
    const response = await api.listManagerTariffsByKind(kind, inactive);
    if (requestId !== tariffRequestId) return;
    tariffs.value = response.items || [];
    if (!selectedTariffId.value && tariffs.value.length) {
      selectedTariffId.value = tariffs.value[0]!.id;
    } else if (selectedTariffId.value && !tariffs.value.some((t) => t.id === selectedTariffId.value)) {
      selectedTariffId.value = tariffs.value[0]?.id ?? null;
    }
  } catch (e) {
    if (requestId !== tariffRequestId) return;
    error.value = getApiErrorMessage(e);
    tariffs.value = [];
    selectedTariffId.value = null;
  } finally {
    if (requestId === tariffRequestId) loading.value = false;
  }
};
const refreshAfterDraftChange = async () => {
  const requestId = ++draftRefreshId;
  draftRefreshLoading.value = true;
  publishError.value = '';
  try {
    await Promise.all([loadTariffs(), kindFilter.value === 'installation' ? loadComparison() : Promise.resolve()]);
  } finally {
    if (requestId === draftRefreshId) draftRefreshLoading.value = false;
  }
};
const handleKindChange = () => {
  comparisonOffset.value = 0;
  if (kindFilter.value === 'installation') void loadComparison();
  else invalidateComparison();
  void loadTariffs();
};
const changeComparisonPage = (delta: number) => {
  if (comparisonLoading.value) return;
  comparisonOffset.value = Math.max(0, comparisonOffset.value + delta);
  void loadComparison();
};

const openAddTariff = () => {
  editingTariff.value = null;
  showTariffModal.value = true;
};

const openEditTariff = (tariff: ManagerTariffResponse) => {
  editingTariff.value = tariff;
  showTariffModal.value = true;
};

const confirmDeleteTariff = async (tariff: ManagerTariffResponse) => {
  if (!await confirmDialog({ title: 'Удалить тариф?', description: tariffShortName(tariff), confirmText: 'Удалить', variant: 'danger' })) return;
  try {
    await api.deleteManagerTariff(tariff.id);
    setToast('Тариф удален');
    await refreshAfterDraftChange();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const openAddRule = (tariffId: number) => {
  selectedTariffId.value = tariffId;
  editingRule.value = null;
  showRuleModal.value = true;
};

const openEditRule = (tariffId: number, rule: ManagerTariffRuleResponse) => {
  selectedTariffId.value = tariffId;
  editingRule.value = rule;
  showRuleModal.value = true;
};

const confirmDeleteRule = async (tariffId: number, rule: ManagerTariffRuleResponse) => {
  if (!await confirmDialog({ title: 'Удалить правило?', description: rule.name, confirmText: 'Удалить', variant: 'danger' })) return;
  try {
    await api.deleteManagerTariffRule(tariffId, rule.id);
    setToast('Правило удалено');
    await refreshAfterDraftChange();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const handleTariffSuccess = async () => {
  setToast('Тариф сохранен');
  await refreshAfterDraftChange();
};

const handleRuleSuccess = async () => {
  setToast('Правило сохранено');
  await refreshAfterDraftChange();
};

onMounted(() => { void loadTariffs(); void loadComparison(); });
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full">
    <Transition name="toast">
      <div
        v-if="toast"
        class="fixed top-20 right-8 z-50 bg-brand-600 border border-brand-500 text-white px-4 py-3 rounded-lg shadow-xl shadow-brand-900/30 flex items-center gap-3"
      >
        <span class="material-icons-round text-xl">check_circle</span>
        <span class="text-sm font-medium">{{ toast }}</span>
      </div>
    </Transition>

    <div class="flex flex-wrap gap-3 items-end justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
          <span class="material-icons-round text-brand-600 dark:text-brand-400">payments</span>
          Тарифы смет
        </h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
          Работы и правила для внутренних смет менеджера
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <label class="text-sm text-gray-600 dark:text-slate-300">Направление</label>
        <select
          v-model="kindFilter"
          class="rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
          @change="handleKindChange"
        >
          <option v-for="option in serviceKindOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <label class="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-slate-300">
          <input v-model="includeInactive" type="checkbox" @change="loadTariffs" />
          Показать неактивные
        </label>
        <button
          @click="openAddTariff"
          class="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white font-medium py-2.5 px-4 rounded-lg shadow-lg shadow-brand-900/40 transition-all text-sm"
        >
          <span class="material-icons-round text-[18px]">add</span>
          Добавить тариф
        </button>
      </div>
    </div>

    <div v-if="kindFilter === 'installation'" class="mb-6 flex flex-col gap-3 rounded-xl border border-blue-200 bg-blue-50 p-4 text-blue-950 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-100 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-start gap-3">
        <span class="material-icons-round mt-0.5 text-blue-600 dark:text-blue-300">info</span>
        <div>
          <div class="text-sm font-semibold">Книга монтажа: {{ comparisonStatus }}</div>
          <div class="mt-0.5 text-xs text-blue-800/80 dark:text-blue-200/80">
            Типизированные тарифы и правила сначала сохраняются как черновик. Публикация проверяет полноту и пересечения; старые публичные цены остаются отдельно.
          </div>
        </div>
      </div>
      <button type="button" :disabled="publishing || !comparisonReady || loading || !!error" class="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50" @click="publish">{{ publishing ? 'Публикуем…' : 'Опубликовать книгу' }}</button>
    </div>
    <div v-if="publishError" role="alert" class="mb-6 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-700">{{ publishError }}</div>

    <div
      v-if="error"
      class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6"
    >
      {{ error }}
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-5 gap-6">
      <section class="xl:col-span-3 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 overflow-x-auto">
        <div v-if="loading" class="flex justify-center py-20">
          <div class="w-8 h-8 rounded-full border-4 border-gray-200 dark:border-slate-700 border-t-brand-500 animate-spin"></div>
        </div>

        <p v-else class="px-4 pt-3 text-xs text-gray-500 dark:text-slate-400 md:hidden">Прокрутите таблицу вправо, чтобы открыть действия с тарифом.</p>

        <table v-if="!loading" class="min-w-[650px] divide-y divide-gray-200 dark:divide-slate-700/50 xl:min-w-full">
          <thead class="bg-gray-50 dark:bg-slate-800/80">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Тариф</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">База</th>
              <th v-if="shouldShowRouteColumn" class="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Трасса</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Правила</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-slate-700/50 bg-white dark:bg-[#1e293b]">
            <tr
              v-for="tariff in tariffs"
              :key="tariff.id"
              class="hover:bg-gray-50 dark:hover:bg-slate-800/50 transition-colors"
              :class="{ 'bg-brand-50/50 dark:bg-brand-900/10': selectedTariffId === tariff.id }"
            >
              <td class="px-4 py-3">
                <button class="text-left" @click="selectedTariffId = tariff.id">
                  <div class="text-sm font-semibold text-gray-900 dark:text-slate-100">{{ tariffShortName(tariff) }}</div>
                  <div class="text-xs text-gray-500 dark:text-slate-400">
                    {{ serviceKindLabel(tariff.service_kind) }} · {{ tariff.service_kind === 'installation' ? (tariff.installation_match ? `Книга: ${tariff.installation_match.product_kind === 'multi_split_system' ? 'Мультисплит' : indoorTypesLabel(tariff.installation_match.indoor_type || '')}` : 'Вне книги') : (tariff.category || '—') }} · {{ tariff.power_range || 'все мощности' }}
                  </div>
                </button>
              </td>
              <td class="px-4 py-3 text-sm font-medium text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                {{ tariff.base_price }} BYN
              </td>
              <td v-if="shouldShowRouteColumn" class="px-4 py-3 text-sm text-gray-700 dark:text-slate-300 whitespace-nowrap">
                {{ tariff.included_route_meters }} м
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-slate-300">
                {{ tariff.rules?.length || 0 }}
              </td>
              <td class="px-4 py-3">
                <div class="flex justify-end gap-2">
                  <button
                    @click="openAddRule(tariff.id)"
                    class="p-2 text-brand-600 hover:text-brand-700 border border-brand-200 hover:bg-brand-50 rounded-lg transition-colors inline-flex items-center"
                    title="Добавить правило"
                  >
                    <span class="material-icons-round text-sm">library_add</span>
                  </button>
                  <button
                    @click="openEditTariff(tariff)"
                    class="p-2 text-gray-500 hover:text-gray-900 border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors inline-flex items-center"
                    title="Редактировать"
                  >
                    <span class="material-icons-round text-sm">edit</span>
                  </button>
                  <button
                    @click="confirmDeleteTariff(tariff)"
                    class="p-2 text-red-500 hover:text-red-700 border border-red-200 hover:bg-red-50 rounded-lg transition-colors inline-flex items-center"
                    title="Удалить"
                  >
                    <span class="material-icons-round text-sm">delete</span>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!tariffs.length && !loading">
              <td :colspan="shouldShowRouteColumn ? 5 : 4" class="px-6 py-12 text-center text-gray-500 dark:text-slate-400">
                Тарифы не найдены
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="xl:col-span-2 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 p-4">
        <div v-if="!selectedTariff" class="text-sm text-gray-500 dark:text-slate-400">
          Выбери тариф слева, чтобы управлять правилами.
        </div>
        <div v-else>
          <div class="flex items-start justify-between gap-3 mb-4">
            <div>
              <h3 class="text-base font-semibold text-gray-900 dark:text-slate-100">{{ tariffShortName(selectedTariff) }}</h3>
              <p class="text-xs text-gray-500 dark:text-slate-400 mt-1">{{ tariffFullDescription(selectedTariff) }}</p>
            </div>
            <button
              @click="openAddRule(selectedTariff.id)"
              class="inline-flex items-center gap-1 rounded-lg border border-brand-300 text-brand-700 px-2 py-1 text-xs font-medium hover:bg-brand-50"
            >
              <span class="material-icons-round text-[15px]">add</span>
              Правило
            </button>
          </div>

          <div v-if="!selectedTariff.rules?.length" class="text-sm text-gray-500 dark:text-slate-400">
            У этого тарифа пока нет правил.
          </div>

          <div v-else class="space-y-2">
            <div
              v-for="rule in selectedTariff.rules"
              :key="rule.id"
              class="rounded-lg border border-gray-200 dark:border-slate-700 p-3 bg-gray-50 dark:bg-slate-800/50"
            >
              <div class="flex items-start justify-between gap-2">
                <div>
                  <div class="text-sm font-semibold text-gray-900 dark:text-slate-100">{{ rule.name }}</div>
                  <div class="text-xs text-gray-500 dark:text-slate-400">
                    {{ rule.component_code || 'Без смысла компонента' }} · {{ rule.unit_price }} BYN/{{ rule.unit }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-slate-400 mt-1">{{ rule.line_template }}</div>
                </div>
                <div class="flex gap-1">
                  <button class="p-1.5 rounded border border-gray-300 hover:bg-gray-100" title="Редактировать правило" @click="openEditRule(selectedTariff.id, rule)">
                    <span class="material-icons-round text-[15px]">edit</span>
                  </button>
                  <button class="p-1.5 rounded border border-red-300 text-red-600 hover:bg-red-50" title="Удалить правило" @click="confirmDeleteRule(selectedTariff.id, rule)">
                    <span class="material-icons-round text-[15px]">delete</span>
                  </button>
                </div>
              </div>
              <div class="mt-1 flex gap-2 text-[11px]">
                <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-700 border border-gray-200 dark:border-slate-600">
                  {{ rule.is_optional ? 'По выбору' : 'Обязательно' }}
                </span>
                <span
                  v-if="rule.is_favorite"
                  class="px-2 py-0.5 rounded bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200 border border-amber-200 dark:border-amber-500/30"
                >
                  Избранное
                </span>
                <span class="px-2 py-0.5 rounded bg-white dark:bg-slate-700 border border-gray-200 dark:border-slate-600">
                  {{ rule.is_active ? 'Активно' : 'Выключено' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <section v-if="kindFilter === 'installation'" class="mt-6 rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
      <h2 class="text-base font-semibold">Сверка со старыми публичными расценками</h2>
      <p class="mt-1 text-xs text-gray-500">Кандидаты черновика найдены только по категории внутреннего блока. Даже одинаковые цены не доказывают соответствие по мощности и трубам. Сверка ничего не переносит в книгу.</p>
      <div v-if="comparisonLoading || draftRefreshLoading" class="mt-3 text-sm">Загружаем сравнение…</div>
      <div v-else-if="comparisonError" role="alert" class="mt-3 text-sm text-red-600">{{ comparisonError }}</div>
      <div v-else-if="!comparison?.items.length" class="mt-3 text-sm text-gray-500">На этой странице старых расценок нет.</div>
      <div v-else class="mt-3 space-y-3">
        <div v-for="row in comparison.items" :key="row.legacy_rate_id" class="grid gap-3 rounded-lg border border-gray-200 p-3 text-sm dark:border-slate-700 md:grid-cols-[14rem_minmax(0,1fr)]">
          <div>
            <div class="text-xs font-semibold uppercase text-gray-500 dark:text-slate-400">Старая расценка</div>
            <div class="mt-1 font-medium">{{ row.legacy_category }} · {{ row.legacy_power_range }}</div>
            <div class="mt-1">База {{ money(row.legacy_base_price) }} BYN</div>
            <div>Доп. трасса {{ money(row.legacy_route_extra_price) }} BYN/м</div>
          </div>
          <div>
            <div class="text-xs font-semibold uppercase text-gray-500 dark:text-slate-400">Кандидаты черновика — только по категории</div>
            <div v-if="!row.candidates?.length" class="mt-1 font-medium text-amber-700 dark:text-amber-300">Нет кандидатов — требуется сопоставление</div>
            <div v-else class="mt-2 space-y-2">
              <div v-for="candidate in row.candidates" :key="candidate.tariff_code" class="rounded-lg bg-gray-50 p-2 dark:bg-slate-900/50">
                <div class="font-medium" :title="candidate.tariff_code">{{ candidateName(candidate) }} <span class="ml-1 text-xs font-normal text-blue-700 dark:text-blue-300">Черновик</span></div>
                <div class="mt-1">{{ candidatePrice(candidate) }}</div>
                <div class="text-xs text-gray-600 dark:text-slate-300">{{ matcherSummary(candidate) }}</div>
                <div class="mt-1 text-xs font-medium text-amber-700 dark:text-amber-300">{{ candidatePriceReview(row, candidate) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="mt-3 flex items-center gap-3 text-sm">
        <button type="button" class="rounded-lg border border-gray-200 px-2 py-1 disabled:opacity-40 dark:border-slate-600" :disabled="comparisonOffset === 0 || !comparisonReady" @click="changeComparisonPage(-100)">Назад</button>
        <span>Записи {{ comparison?.items.length ? comparisonOffset + 1 : 0 }}–{{ comparisonOffset + (comparison?.items.length ?? 0) }}</span>
        <button type="button" class="rounded-lg border border-gray-200 px-2 py-1 disabled:opacity-40 dark:border-slate-600" :disabled="!comparisonReady || (comparison?.items.length ?? 0) < 100" @click="changeComparisonPage(100)">Далее</button>
      </div>
    </section>

    <TariffEditModal
      v-model="showTariffModal"
      :tariff="editingTariff"
      :initial-service-kind="kindFilter"
      @success="handleTariffSuccess"
    />
    <TariffRuleEditModal
      v-model="showRuleModal"
      :tariff-id="selectedTariffId"
      :tariff="selectedTariff"
      :rule="editingRule"
      @success="handleRuleSuccess"
    />
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
