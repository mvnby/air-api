<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../api';
import type {
  ManagerTariffCreatePayload,
  ManagerTariffResponse,
  ManagerTariffServiceKind,
  ManagerTariffUpdatePayload,
  InstallationMatcher_Input,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
  modelValue: boolean;
  tariff?: ManagerTariffResponse | null;
  initialServiceKind?: ManagerTariffServiceKind;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');
type IndoorType = InstallationMatcher_Input['indoor_type'];
const indoorTypes: Array<{ value: IndoorType; label: string }> = [
  { value: 'wall', label: 'Настенный' }, { value: 'cassette', label: 'Кассетный' },
  { value: 'duct', label: 'Канальный' }, { value: 'floor_ceiling', label: 'Напольно-потолочный' },
  { value: 'column', label: 'Колонный' }, { value: 'console', label: 'Консольный' },
];
const indoorType = ref<IndoorType | ''>('');
const capacityMin = ref<number | null>(null);
const capacityMax = ref<number | null>(null);
const pipeLiquid = ref('');
const pipeGas = ref('');
const weightSource = ref<InstallationMatcher_Input['weight_source']>(null);
const weightMin = ref<number | null>(null);
const weightMax = ref<number | null>(null);
const includedDiamondHoles = ref(0);
const priceMode = ref<'fixed' | 'from' | 'quote'>('fixed');
const existingInstallationCode = ref<string | null>(null);
const existingHoles = ref<Record<string, number>>({});
const numberOrNull = (value: number | null): number | null => value === null || value === undefined || String(value).trim() === '' ? null : Number(value);
const installationFields = (): Pick<ManagerTariffCreatePayload, 'installation_code' | 'installation_match' | 'installation_price_mode' | 'included_holes_by_type'> => {
  if (formData.value.service_kind !== 'installation' || !indoorType.value) {
    return { installation_code: null, installation_match: null, installation_price_mode: 'fixed', included_holes_by_type: {} };
  }
  const code = existingInstallationCode.value || `installation.${indoorType.value}.${crypto.randomUUID().slice(0, 8)}`;
  const holes = { ...existingHoles.value };
  if (includedDiamondHoles.value > 0 || 'diamond' in holes) holes.diamond = includedDiamondHoles.value;
  return {
    installation_code: code,
    installation_match: {
      product_kind: 'complete_split_system', indoor_type: indoorType.value,
      capacity_min_kw: numberOrNull(capacityMin.value), capacity_max_kw: numberOrNull(capacityMax.value),
      pipe_liquid: pipeLiquid.value.trim() || null, pipe_gas: pipeGas.value.trim() || null,
      weight_source: weightSource.value || null,
      weight_min_kg: weightSource.value ? numberOrNull(weightMin.value) : null,
      weight_max_kg: weightSource.value ? numberOrNull(weightMax.value) : null,
    },
    installation_price_mode: priceMode.value,
    included_holes_by_type: holes,
  };
};

const serviceKindOptions: Array<{ value: ManagerTariffServiceKind; label: string }> = [
  { value: 'installation', label: 'Монтаж' },
  { value: 'pre_install', label: 'Закладка коммуникаций' },
  { value: 'dismantling', label: 'Демонтаж' },
  { value: 'maintenance', label: 'Обслуживание' },
  { value: 'repair', label: 'Ремонт' },
];

const ROUTE_AWARE_SERVICE_KINDS = new Set<ManagerTariffServiceKind>(['installation', 'pre_install']);
const isRouteAwareServiceKind = computed(() => ROUTE_AWARE_SERVICE_KINDS.has(formData.value.service_kind as ManagerTariffServiceKind));

const categoryPlaceholder = computed(() => {
  if (formData.value.service_kind === 'repair') return 'diagnostics / compressor / leak';
  if (formData.value.service_kind === 'maintenance') return 'split / cassette / duct';
  if (formData.value.service_kind === 'dismantling') return 'Wall / Cassette / Duct';
  if (formData.value.service_kind === 'pre_install') return 'Wall';
  return 'Wall / Cassette / Duct';
});

const powerPlaceholder = computed(() => {
  if (formData.value.service_kind === 'repair') return 'бытовой / полупром / до 7 кВт';
  if (formData.value.service_kind === 'maintenance') return 'до 3.5 кВт / до 7 кВт';
  if (formData.value.service_kind === 'pre_install') return '07-12 / до 3.5 кВт';
  return '07-12 / до 3.5 кВт';
});

const formData = ref<ManagerTariffCreatePayload>({
  service_kind: 'installation',
  short_name: '',
  full_description: null,
  category: '',
  power_range: '',
  base_price: 0,
  included_route_meters: 3,
  is_active: true,
  sort_order: 0,
  comment: null,
});

const resetForm = () => {
  const matcher = props.tariff?.installation_match;
  indoorType.value = matcher?.indoor_type ?? '';
  capacityMin.value = matcher?.capacity_min_kw == null ? null : Number(matcher.capacity_min_kw);
  capacityMax.value = matcher?.capacity_max_kw == null ? null : Number(matcher.capacity_max_kw);
  pipeLiquid.value = matcher?.pipe_liquid ?? '';
  pipeGas.value = matcher?.pipe_gas ?? '';
  weightSource.value = matcher?.weight_source ?? null;
  weightMin.value = matcher?.weight_min_kg == null ? null : Number(matcher.weight_min_kg);
  weightMax.value = matcher?.weight_max_kg == null ? null : Number(matcher.weight_max_kg);
  existingHoles.value = { ...(props.tariff?.included_holes_by_type ?? {}) };
  includedDiamondHoles.value = existingHoles.value.diamond ?? 0;
  priceMode.value = props.tariff?.installation_price_mode ?? 'fixed';
  existingInstallationCode.value = props.tariff?.installation_code ?? null;
  if (props.tariff) {
    formData.value = {
      service_kind: props.tariff.service_kind,
      short_name: props.tariff.short_name || props.tariff.selector_label,
      full_description: props.tariff.full_description || null,
      category: props.tariff.category,
      power_range: props.tariff.power_range,
      base_price: props.tariff.base_price,
      included_route_meters: props.tariff.included_route_meters,
      is_active: props.tariff.is_active,
      sort_order: props.tariff.sort_order,
      comment: props.tariff.comment || null,
    };
  } else {
    const serviceKind = props.initialServiceKind ?? 'installation';
    formData.value = {
      service_kind: serviceKind,
      short_name: '',
      full_description: null,
      category: '',
      power_range: '',
      base_price: 0,
      included_route_meters: ROUTE_AWARE_SERVICE_KINDS.has(serviceKind) ? 3 : 0,
      is_active: true,
      sort_order: 0,
      comment: null,
    };
  }
  error.value = '';
};

const handleServiceKindChange = () => {
  const serviceKind = formData.value.service_kind as ManagerTariffServiceKind;
  if (!ROUTE_AWARE_SERVICE_KINDS.has(serviceKind)) {
    formData.value.included_route_meters = 0;
  } else if (!formData.value.included_route_meters) {
    formData.value.included_route_meters = 3;
  }
};

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      resetForm();
    }
  },
  { immediate: true }
);

const close = () => {
  if (!loading.value) emit('update:modelValue', false);
};

const submit = async () => {
  if (!String(formData.value.short_name || '').trim()) {
    error.value = 'Короткое название обязательно';
    return;
  }
  if (formData.value.service_kind === 'installation' && indoorType.value) {
    if ((!pipeLiquid.value.trim() && pipeGas.value.trim()) || (pipeLiquid.value.trim() && !pipeGas.value.trim())) {
      error.value = 'Укажите обе трубы пары или оставьте обе пустыми'; return;
    }
    if (!Number.isInteger(includedDiamondHoles.value) || includedDiamondHoles.value < 0) {
      error.value = 'Количество включённых отверстий должно быть целым неотрицательным'; return;
    }
  }
  loading.value = true;
  error.value = '';
  try {
    const normalizedIncludedRoute = ROUTE_AWARE_SERVICE_KINDS.has(formData.value.service_kind as ManagerTariffServiceKind)
      ? formData.value.included_route_meters
      : 0;
    const canonicalFields = installationFields();
    if (props.tariff?.id) {
      const updatePayload: ManagerTariffUpdatePayload = {
        service_kind: formData.value.service_kind as ManagerTariffServiceKind,
        short_name: formData.value.short_name,
        full_description: formData.value.full_description || null,
        category: formData.value.category,
        power_range: formData.value.power_range,
        base_price: formData.value.base_price,
        included_route_meters: normalizedIncludedRoute,
        is_active: formData.value.is_active,
        sort_order: formData.value.sort_order,
        comment: formData.value.comment,
        ...canonicalFields,
      };
      await api.updateManagerTariff(props.tariff.id, updatePayload);
    } else {
      await api.createManagerTariff({
        ...formData.value,
        included_route_meters: normalizedIncludedRoute,
        ...canonicalFields,
      });
    }
    emit('success');
    close();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      >
        <div class="modal-content bg-white dark:bg-[#1e293b] rounded-xl shadow-xl w-full max-w-2xl overflow-hidden border border-gray-200 dark:border-slate-700/60 flex flex-col">
          <div class="px-6 py-4 border-b border-gray-200 dark:border-slate-700/50 flex justify-between items-center bg-gray-50 dark:bg-slate-800/50">
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ tariff ? 'Редактировать тариф сметы' : 'Новый тариф сметы' }}
            </h3>
            <button
              @click="close"
              class="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-white transition-colors"
              :disabled="loading"
            >
              <span class="material-icons-round text-xl">close</span>
            </button>
          </div>

          <div class="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
            <div
              v-if="error"
              class="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-500/50 rounded-lg text-sm text-red-600 dark:text-red-400"
            >
              {{ error }}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Направление</span>
                <select
                  v-model="formData.service_kind"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :disabled="loading"
                  @change="handleServiceKindChange"
                >
                  <option v-for="option in serviceKindOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>

              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Порядок</span>
                <input
                  v-model.number="formData.sort_order"
                  type="number"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>
            </div>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Короткое название *</span>
              <input
                v-model="formData.short_name"
                type="text"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                placeholder="Монтаж настенного до 3.5 кВт"
                :disabled="loading"
              />
            </label>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Подробное описание</span>
              <textarea
                v-model="formData.full_description"
                rows="5"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 resize-none"
                placeholder="Состав работ для подробных документов. Если оставить пустым, будет использовано короткое название."
                :disabled="loading"
              />
            </label>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Группа в смете</span>
                <input
                  v-model="formData.category"
                  type="text"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :placeholder="categoryPlaceholder"
                  :disabled="loading"
                />
              </label>
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Уточнение для сметы</span>
                <input
                  v-model="formData.power_range"
                  type="text"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :placeholder="powerPlaceholder"
                  :disabled="loading"
                />
              </label>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Базовая цена (BYN)</span>
                <input
                  v-model.number="formData.base_price"
                  type="number"
                  min="0"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>
              <label v-if="isRouteAwareServiceKind" class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Включено трассы, м</span>
                <input
                  v-model.number="formData.included_route_meters"
                  type="number"
                  min="0"
                  step="0.5"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>
            </div>

            <div v-if="formData.service_kind === 'installation'" class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700">
              <div class="text-sm font-semibold text-gray-900 dark:text-white">Подбор канонического монтажа</div>
              <p class="text-xs text-gray-500 dark:text-slate-400">Выбор типа добавляет тариф в черновик книги. Сохранение не публикует цены. Старые тарифы без типа остаются как есть.</p>
              <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label class="block text-sm">Тип внутреннего блока
                  <select v-model="indoorType" aria-label="Тип внутреннего блока" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" :disabled="loading">
                    <option value="">Не включать в книгу</option>
                    <option v-for="option in indoorTypes" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </label>
                <label v-if="indoorType" class="block text-sm">Режим цены
                  <select v-model="priceMode" aria-label="Режим цены" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" :disabled="loading">
                    <option value="fixed">Фиксированная</option><option value="from">От указанной суммы</option><option value="quote">По запросу</option>
                  </select>
                </label>
              </div>
              <template v-if="indoorType">
                <div v-if="tariff?.installation_code" class="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
                  <span>{{ existingInstallationCode ? 'Условия опубликованного подбора менять нельзя. Если условия изменились, создайте новый подбор.' : 'При сохранении для новых условий будет создан новый внутренний код.' }}</span>
                  <button v-if="existingInstallationCode" type="button" class="font-medium text-brand-700 dark:text-brand-300" @click="existingInstallationCode = null">Новые условия подбора</button>
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <label class="text-sm">Мощность от, кВт<input v-model.number="capacityMin" aria-label="Мощность от, кВт" type="number" min="0" step="0.001" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" /></label>
                  <label class="text-sm">Мощность до, кВт<input v-model.number="capacityMax" aria-label="Мощность до, кВт" type="number" min="0" step="0.001" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" /></label>
                  <label class="text-sm">Жидкостная труба<input v-model="pipeLiquid" aria-label="Жидкостная труба" placeholder="1/4&quot;" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" /></label>
                  <label class="text-sm">Газовая труба<input v-model="pipeGas" aria-label="Газовая труба" placeholder="3/8&quot;" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" /></label>
                </div>
                <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <label class="text-sm">Источник веса<select v-model="weightSource" aria-label="Источник веса" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900"><option :value="null">Не учитывать</option><option value="weight_indoor">Внутренний блок</option><option value="weight_outdoor">Наружный блок</option></select></label>
                  <label class="text-sm">Вес от, кг<input v-model.number="weightMin" aria-label="Вес от, кг" type="number" min="0" step="0.01" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" :disabled="!weightSource" /></label>
                  <label class="text-sm">Вес до, кг<input v-model.number="weightMax" aria-label="Вес до, кг" type="number" min="0" step="0.01" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" :disabled="!weightSource" /></label>
                </div>
                <label class="block text-sm">Включено алмазных отверстий<input v-model.number="includedDiamondHoles" aria-label="Включено алмазных отверстий" type="number" min="0" step="1" class="mt-1 w-full rounded-lg border p-2 dark:bg-slate-900" /></label>
                <p class="text-xs text-gray-500 dark:text-slate-400">Для фиксированной цены и цены «от» при публикации нужны мощность, пара труб, цена базы и цена дополнительной трассы. Для включённых отверстий нужна цена превышения.</p>
              </template>
            </div>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Комментарий</span>
              <textarea
                v-model="formData.comment"
                rows="2"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 resize-none"
                :disabled="loading"
              />
            </label>

            <label class="inline-flex items-center gap-2">
              <input v-model="formData.is_active" type="checkbox" class="h-4 w-4" :disabled="loading" />
              <span class="text-sm text-gray-700 dark:text-slate-300">Тариф активен</span>
            </label>
          </div>

          <div class="px-6 py-4 border-t border-gray-200 dark:border-slate-700/50 bg-gray-50 dark:bg-slate-800/30 flex justify-end gap-3">
            <button
              @click="close"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-300 hover:text-gray-900 dark:hover:text-white bg-transparent hover:bg-gray-200 dark:hover:bg-slate-700 transition-colors rounded-lg"
              :disabled="loading"
            >
              Отмена
            </button>
            <button
              @click="submit"
              class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-brand-600 hover:bg-brand-500 active:bg-brand-700 transition-colors rounded-lg disabled:opacity-50 shadow-lg shadow-brand-900/30"
              :disabled="loading || !String(formData.short_name || '').trim()"
            >
              <span v-if="loading" class="material-icons-round text-sm animate-spin">refresh</span>
              <span v-else class="material-icons-round text-sm">save</span>
              Сохранить
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-active .modal-content,
.modal-fade-leave-active .modal-content {
  transition: transform 0.2s ease;
}
.modal-fade-enter-from .modal-content,
.modal-fade-leave-to .modal-content {
  transform: scale(0.95);
}
</style>
