<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../api';
import type {
  ManagerTariffCreatePayload,
  ManagerTariffResponse,
  ManagerTariffServiceKind,
  ManagerTariffUpdatePayload,
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

const DEFAULT_TEMPLATES: Record<ManagerTariffServiceKind, string> = {
  installation: 'Монтаж сплит-системы, включая расходные материалы',
  pre_install: 'Закладка межблочной трассы под кондиционер, включая материалы',
  dismantling: 'Демонтаж кондиционера',
  maintenance: 'Техническое обслуживание кондиционера',
  repair: 'Ремонт кондиционера',
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
  selector_label: '',
  estimate_template: DEFAULT_TEMPLATES.installation,
  category: '',
  power_range: '',
  base_price: 0,
  included_route_meters: 3,
  is_active: true,
  sort_order: 0,
  comment: null,
});

const resetForm = () => {
  if (props.tariff) {
    formData.value = {
      service_kind: props.tariff.service_kind,
      selector_label: props.tariff.selector_label,
      estimate_template: props.tariff.estimate_template,
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
      selector_label: '',
      estimate_template: DEFAULT_TEMPLATES[serviceKind],
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
  const currentTemplate = String(formData.value.estimate_template || '').trim();
  if (!currentTemplate || Object.values(DEFAULT_TEMPLATES).includes(currentTemplate)) {
    formData.value.estimate_template = DEFAULT_TEMPLATES[serviceKind];
  }
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
  }
);

const close = () => {
  if (!loading.value) emit('update:modelValue', false);
};

const submit = async () => {
  if (!String(formData.value.selector_label || '').trim()) {
    error.value = 'Короткое название обязательно';
    return;
  }
  if (!String(formData.value.estimate_template || '').trim()) {
    error.value = 'Шаблон формулировки обязателен';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    const normalizedIncludedRoute = ROUTE_AWARE_SERVICE_KINDS.has(formData.value.service_kind as ManagerTariffServiceKind)
      ? formData.value.included_route_meters
      : 0;
    if (props.tariff?.id) {
      const updatePayload: ManagerTariffUpdatePayload = {
        service_kind: formData.value.service_kind as ManagerTariffServiceKind,
        selector_label: formData.value.selector_label,
        estimate_template: formData.value.estimate_template,
        category: formData.value.category,
        power_range: formData.value.power_range,
        base_price: formData.value.base_price,
        included_route_meters: normalizedIncludedRoute,
        is_active: formData.value.is_active,
        sort_order: formData.value.sort_order,
        comment: formData.value.comment,
      };
      await api.updateManagerTariff(props.tariff.id, updatePayload);
    } else {
      await api.createManagerTariff({
        ...formData.value,
        included_route_meters: normalizedIncludedRoute,
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
              {{ tariff ? 'Редактировать базовый тариф' : 'Новый базовый тариф' }}
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
                v-model="formData.selector_label"
                type="text"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                placeholder="Монтаж настенного до 3.5 кВт"
                :disabled="loading"
              />
            </label>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Шаблон формулировки *</span>
              <textarea
                v-model="formData.estimate_template"
                rows="2"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200 resize-none"
                :disabled="loading"
              />
            </label>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Категория</span>
                <input
                  v-model="formData.category"
                  type="text"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :placeholder="categoryPlaceholder"
                  :disabled="loading"
                />
              </label>
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Диапазон мощности</span>
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
              class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 active:bg-teal-700 transition-colors rounded-lg disabled:opacity-50 shadow-lg shadow-teal-900/30"
              :disabled="loading || !String(formData.selector_label || '').trim()"
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
