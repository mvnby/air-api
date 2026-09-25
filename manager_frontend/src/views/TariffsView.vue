<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api } from '../api';
import type {
  ManagerTariffResponse,
  ManagerTariffRuleResponse,
  ManagerTariffServiceKind,
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
const publishing = ref(false);
const publishError = ref('');
const publishErrors: Record<string, string> = {
  empty_price_book: 'Нет активных тарифов с типизированным подбором.',
  incomplete_fixed_matcher: 'Для фиксированной цены или цены «от» укажите границу мощности и обе трубы пары.',
  missing_base_price: 'Для фиксированной цены или цены «от» нужна положительная базовая цена.',
  missing_route_price: 'Добавьте правило «Трасса сверх включённой» с ценой.',
  missing_hole_price: 'Для включённых отверстий добавьте цену отверстия сверх включённого.',
  missing_component_code: 'У активного правила не указан смысл компонента.',
  matcher_conflict: 'Два тарифа пересекаются по условиям подбора с одинаковой точностью.',
  duplicate_component_code: 'В одном тарифе два правила с одинаковым смыслом.',
  site_extra_conflict: 'Цена общих работ на объекте различается между тарифами.',
  invalid_component_rule: 'Тип расчёта или единица правила не совпадает с выбранным компонентом.',
  tariff_code_reused: 'Условия уже опубликованного тарифа изменены. Откройте тариф и создайте для нового подбора новый код.',
  component_code_reused: 'Смысл опубликованного компонента нельзя менять. Выберите другой компонент.',
  duplicate_tariff_code: 'Два активных тарифа имеют один код установки.',
  packed_weight_requires_transport_rule: 'Для подбора монтажа используйте вес блока без упаковки.',
};
const loadComparison = async () => {
  comparisonLoading.value = true;
  comparisonError.value = '';
  try { comparison.value = await api.listManagerInstallationLegacyComparison(comparisonOffset.value); }
  catch (e) { comparisonError.value = getApiErrorMessage(e); comparison.value = null; }
  finally { comparisonLoading.value = false; }
};
const publish = async () => {
  if (!await confirmDialog({ title: 'Опубликовать книгу монтажа?', description: 'Активные тарифы с типизированным подбором станут новой неизменяемой ревизией. Старые публичные расценки не копируются и не меняются.', confirmText: 'Опубликовать' })) return;
  publishing.value = true;
  publishError.value = '';
  try {
    const result = await api.publishManagerInstallationPriceBook();
    setToast(`Опубликована ревизия ${result.revision}`);
    await loadComparison();
  } catch (e) {
    const detail = (e as { body?: { detail?: { code?: string } } })?.body?.detail;
    publishError.value = (e as { status?: number })?.status === 403
      ? 'Нет прав на публикацию книги монтажа.'
      : `${detail?.code && publishErrors[detail.code] ? `${publishErrors[detail.code]} ` : ''}${getApiErrorMessage(e)}`;
  } finally { publishing.value = false; }
};
const comparisonStatus = (status: string) => status === 'unmapped_review_required'
  ? 'Нет кандидатов — требуется сопоставление'
  : status === 'price_equal_review_required'
    ? 'Цена совпадает, соответствие требует проверки'
    : 'Цена отличается, соответствие требует проверки';

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

const ROUTE_AWARE_SERVICE_KINDS = new Set<ManagerTariffServiceKind>(['installation', 'pre_install']);
const shouldShowRouteColumn = computed(() => ROUTE_AWARE_SERVICE_KINDS.has(kindFilter.value));

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};

const loadTariffs = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await api.listManagerTariffsByKind(kindFilter.value, includeInactive.value);
    tariffs.value = response.items || [];
    if (!selectedTariffId.value && tariffs.value.length) {
      selectedTariffId.value = tariffs.value[0]!.id;
    } else if (selectedTariffId.value && !tariffs.value.some((t) => t.id === selectedTariffId.value)) {
      selectedTariffId.value = tariffs.value[0]?.id ?? null;
    }
  } catch (e) {
    error.value = getApiErrorMessage(e);
    tariffs.value = [];
    selectedTariffId.value = null;
  } finally {
    loading.value = false;
  }
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
    await loadTariffs();
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
    await loadTariffs();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const handleTariffSuccess = async () => {
  setToast('Тариф сохранен');
  await loadTariffs();
};

const handleRuleSuccess = async () => {
  setToast('Правило сохранено');
  await loadTariffs();
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
          @change="loadTariffs"
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
          <div class="text-sm font-semibold">Книга монтажа: {{ comparison?.price_book_revision ? `ревизия ${comparison.price_book_revision} опубликована` : 'ещё не опубликована' }}</div>
          <div class="mt-0.5 text-xs text-blue-800/80 dark:text-blue-200/80">
            Типизированные тарифы и правила сначала сохраняются как черновик. Публикация проверяет полноту и пересечения; старые публичные цены остаются отдельно.
          </div>
        </div>
      </div>
      <button type="button" :disabled="publishing || comparisonLoading" class="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50" @click="publish">{{ publishing ? 'Публикуем…' : 'Опубликовать книгу' }}</button>
    </div>
    <div v-if="publishError" role="alert" class="mb-6 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-700">{{ publishError }}</div>

    <div
      v-if="error"
      class="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/50 text-red-600 dark:text-red-400 p-4 rounded-xl mb-6"
    >
      {{ error }}
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-5 gap-6">
      <section class="xl:col-span-3 bg-white dark:bg-[#1e293b] rounded-xl shadow-sm border border-gray-200 dark:border-slate-700/60 overflow-hidden">
        <div v-if="loading" class="flex justify-center py-20">
          <div class="w-8 h-8 rounded-full border-4 border-gray-200 dark:border-slate-700 border-t-brand-500 animate-spin"></div>
        </div>

        <table v-else class="min-w-full divide-y divide-gray-200 dark:divide-slate-700/50">
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
                    {{ serviceKindLabel(tariff.service_kind) }} · {{ tariff.service_kind === 'installation' ? (tariff.installation_match ? `Книга: ${indoorTypesLabel(tariff.installation_match.indoor_type)}` : 'Вне книги') : (tariff.category || '—') }} · {{ tariff.power_range || 'все мощности' }}
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
                  <button class="p-1.5 rounded border border-gray-300 hover:bg-gray-100" @click="openEditRule(selectedTariff.id, rule)">
                    <span class="material-icons-round text-[15px]">edit</span>
                  </button>
                  <button class="p-1.5 rounded border border-red-300 text-red-600 hover:bg-red-50" @click="confirmDeleteRule(selectedTariff.id, rule)">
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
      <p class="mt-1 text-xs text-gray-500">Кандидаты найдены только по категории внутреннего блока. Даже одинаковая цена не доказывает точное соответствие. Сверка ничего не переносит в книгу.</p>
      <div v-if="comparisonLoading" class="mt-3 text-sm">Загружаем сравнение…</div>
      <div v-else-if="comparisonError" role="alert" class="mt-3 text-sm text-red-600">{{ comparisonError }}</div>
      <div v-else-if="!comparison?.items.length" class="mt-3 text-sm text-gray-500">На этой странице старых расценок нет.</div>
      <div v-else class="mt-3 overflow-x-auto">
        <table class="w-full text-left text-sm"><thead><tr><th class="py-2">Старая расценка</th><th>Кандидаты книги</th><th>Проверка</th></tr></thead>
          <tbody><tr v-for="row in comparison.items" :key="row.legacy_rate_id" class="border-t border-gray-200 dark:border-slate-700">
            <td class="py-2">{{ row.legacy_category }} · {{ row.legacy_power_range }} · {{ row.legacy_base_price }} BYN</td>
            <td>{{ row.candidates?.map(candidate => candidate.tariff_code).join(', ') || '—' }}</td>
            <td>{{ comparisonStatus(row.status) }}</td>
          </tr></tbody>
        </table>
      </div>
      <div class="mt-3 flex items-center gap-3 text-sm">
        <button type="button" :disabled="comparisonOffset === 0 || comparisonLoading" @click="comparisonOffset -= 100; loadComparison()">Назад</button>
        <span>Записи {{ comparisonOffset + 1 }}–{{ comparisonOffset + (comparison?.items.length ?? 0) }}</span>
        <button type="button" :disabled="comparisonLoading || (comparison?.items.length ?? 0) < 100" @click="comparisonOffset += 100; loadComparison()">Далее</button>
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
