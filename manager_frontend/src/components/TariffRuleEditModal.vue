<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../api';
import type {
  ManagerTariffResponse,
  ManagerTariffRuleCreatePayload,
  ManagerTariffRuleResponse,
  ManagerTariffRuleType,
  ManagerTariffRuleUpdatePayload,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
  modelValue: boolean;
  tariffId: number | null;
  tariff?: ManagerTariffResponse | null;
  rule?: ManagerTariffRuleResponse | null;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');
const hint = ref('');
const lineTemplateInput = ref<HTMLInputElement | null>(null);
const favoriteRules = ref<ManagerTariffRuleResponse[]>([]);
const favoriteRulesLoading = ref(false);
const favoriteRulesError = ref('');

type RuleTypeOption = {
  value: ManagerTariffRuleType;
  label: string;
  description: string;
  formula: string;
};

type PlaceholderHint = {
  token: string;
  title: string;
  description: string;
};

const ruleTypeOptions: RuleTypeOption[] = [
  {
    value: 'fixed_once',
    label: 'Фиксированная доплата (1 раз)',
    description: 'Разовая позиция без умножения на метры/отверстия.',
    formula: 'Сумма = qty × цена. Обычно qty = 1.',
  },
  {
    value: 'per_unit_manual',
    label: 'Ручное количество (за единицу)',
    description: 'Количество вводится вручную в форме сметы.',
    formula: 'Сумма = qty × цена × количество комплектов.',
  },
  {
    value: 'per_meter_over_included',
    label: 'Доп. трасса сверх включенной',
    description: 'Считается автоматически от длины трассы.',
    formula: 'Сумма = max(длина - включено, 0) × цена × количество комплектов.',
  },
  {
    value: 'per_hole_manual',
    label: 'Доп. отверстия',
    description: 'Считается автоматически по полю “Доп. отверстия”.',
    formula: 'Сумма = количество отверстий × цена × количество комплектов.',
  },
];

const placeholderHints: PlaceholderHint[] = [
  {
    token: '{name}',
    title: 'Название правила',
    description: 'Подставляет текст из поля “Название”.',
  },
  {
    token: '{qty}',
    title: 'Количество',
    description: 'Фактическое количество для этой строки сметы.',
  },
  {
    token: '{unit}',
    title: 'Единица измерения',
    description: 'Подставляет значение из поля “Ед. измерения”.',
  },
  {
    token: '{route_length_m}',
    title: 'Длина трассы',
    description: 'Общая длина трассы из формы сметы (в метрах).',
  },
  {
    token: '{included_route_meters}',
    title: 'Включено в тариф',
    description: 'Сколько метров трассы включено в базовый тариф.',
  },
  {
    token: '{extra_route_meters}',
    title: 'Сверх включенного',
    description: 'Только “лишние” метры трассы сверх лимита.',
  },
  {
    token: '{extra_holes_count}',
    title: 'Доп. отверстия',
    description: 'Количество доп. отверстий из формы сметы.',
  },
];

const serviceKind = computed(() => props.tariff?.service_kind ?? 'installation');
const ROUTE_AWARE_SERVICE_KINDS = new Set(['installation', 'pre_install']);
const isRouteAwareServiceKind = computed(() => ROUTE_AWARE_SERVICE_KINDS.has(String(serviceKind.value)));
const defaultRuleType = computed<ManagerTariffRuleType>(() => (isRouteAwareServiceKind.value ? 'per_unit_manual' : 'fixed_once'));
const availableRuleTypeOptions = computed(() => {
  const allowed = isRouteAwareServiceKind.value
    ? ruleTypeOptions
    : ruleTypeOptions.filter((option) => option.value === 'fixed_once' || option.value === 'per_unit_manual');
  if (!allowed.some((option) => option.value === formData.value.rule_type)) {
    return [
      ...allowed,
      ...ruleTypeOptions.filter((option) => option.value === formData.value.rule_type),
    ];
  }
  return allowed;
});
const displayedPlaceholderHints = computed(() =>
  isRouteAwareServiceKind.value
    ? placeholderHints
    : placeholderHints.filter(
        (item) => !['{route_length_m}', '{included_route_meters}', '{extra_route_meters}', '{extra_holes_count}'].includes(item.token)
      )
);

const selectedRuleTypeOption = computed(
  () => ruleTypeOptions.find((item) => item.value === formData.value.rule_type) ?? ruleTypeOptions[0]
);

const formData = ref<ManagerTariffRuleCreatePayload>({
  rule_type: 'per_unit_manual',
  name: '',
  line_template: '{name}',
  unit: 'шт',
  unit_price: 0,
  is_optional: false,
  is_favorite: false,
  is_active: true,
  sort_order: 0,
  service_id: null,
});

const loadFavoriteRules = async () => {
  if (!props.modelValue || !props.tariff) return;
  favoriteRulesLoading.value = true;
  favoriteRulesError.value = '';
  try {
    const response = await api.listManagerFavoriteTariffRules(serviceKind.value, false, props.tariffId ?? undefined);
    favoriteRules.value = response.items || [];
  } catch (e) {
    favoriteRules.value = [];
    favoriteRulesError.value = getApiErrorMessage(e);
  } finally {
    favoriteRulesLoading.value = false;
  }
};

const resetForm = () => {
  if (props.rule) {
    formData.value = {
      rule_type: props.rule.rule_type,
      name: props.rule.name,
      line_template: props.rule.line_template,
      unit: props.rule.unit,
      unit_price: props.rule.unit_price,
      is_optional: props.rule.is_optional,
      is_favorite: props.rule.is_favorite,
      is_active: props.rule.is_active,
      sort_order: props.rule.sort_order,
      service_id: props.rule.service_id ?? null,
    };
  } else {
    formData.value = {
      rule_type: defaultRuleType.value,
      name: '',
      line_template: '{name}',
      unit: 'шт',
      unit_price: 0,
      is_optional: false,
      is_favorite: false,
      is_active: true,
      sort_order: 0,
      service_id: null,
    };
  }
  error.value = '';
  hint.value = '';
};

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      resetForm();
      void loadFavoriteRules();
    }
  }
);

watch(
  () => props.tariff?.service_kind,
  () => {
    if (props.modelValue) void loadFavoriteRules();
  }
);

const close = () => {
  if (!loading.value) emit('update:modelValue', false);
};

const submit = async () => {
  if (loading.value) return;
  if (!props.tariffId) {
    error.value = 'Не выбран тариф';
    return;
  }
  if (!String(formData.value.name || '').trim()) {
    error.value = 'Название правила обязательно';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    if (props.rule?.id) {
      const payload: ManagerTariffRuleUpdatePayload = { ...formData.value };
      await api.updateManagerTariffRule(props.tariffId, props.rule.id, payload);
    } else {
      await api.createManagerTariffRule(props.tariffId, formData.value);
    }
    emit('success');
    close();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const setDefaultsByType = (type: ManagerTariffRuleType) => {
  if (type === 'per_meter_over_included') {
    formData.value.unit = 'м';
    if (!formData.value.line_template || formData.value.line_template === '{name}') {
      formData.value.line_template = 'доп. трасса {qty} {unit}';
    }
    formData.value.is_optional = false;
  } else if (type === 'per_hole_manual') {
    formData.value.unit = 'шт';
    if (!formData.value.line_template || formData.value.line_template === '{name}') {
      formData.value.line_template = '{extra_holes_count} доп. отверстий';
    }
    formData.value.is_optional = false;
  } else if (type === 'fixed_once') {
    if (!formData.value.line_template || formData.value.line_template === '{name}') {
      formData.value.line_template = '{name}';
    }
  } else if (type === 'per_unit_manual') {
    formData.value.unit = 'шт';
    if (!formData.value.line_template || formData.value.line_template === '{name}') {
      formData.value.line_template = '{name} ({qty} {unit})';
    }
  }
};

const applyFavoriteRule = (rule: ManagerTariffRuleResponse) => {
  formData.value.rule_type = rule.rule_type;
  formData.value.name = rule.name;
  formData.value.line_template = rule.line_template;
  formData.value.unit = rule.unit;
  formData.value.unit_price = rule.unit_price;
  formData.value.is_optional = rule.is_optional;
  formData.value.is_favorite = false;
  formData.value.is_active = true;
  formData.value.service_id = rule.service_id ?? null;
  setHint(`Добавлено из избранного: ${rule.name}`);
};

const setHint = (message: string) => {
  hint.value = message;
  window.setTimeout(() => {
    if (hint.value === message) hint.value = '';
  }, 2500);
};

const copyToClipboard = async (value: string): Promise<boolean> => {
  if (!navigator?.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
};

const insertPlaceholder = async (token: string) => {
  const input = lineTemplateInput.value;
  if (!input || input.disabled) return;

  const current = formData.value.line_template ?? '';
  const start = input.selectionStart ?? current.length;
  const end = input.selectionEnd ?? current.length;
  const before = current.slice(0, start);
  const after = current.slice(end);
  formData.value.line_template = `${before}${token}${after}`;

  const nextCaret = start + token.length;
  window.requestAnimationFrame(() => {
    input.focus();
    input.setSelectionRange(nextCaret, nextCaret);
  });

  const copied = await copyToClipboard(token);
  setHint(copied ? `${token} вставлен и скопирован` : `${token} вставлен`);
};
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      >
        <div class="modal-content bg-white dark:bg-[#1e293b] rounded-xl shadow-xl w-full max-w-xl overflow-hidden border border-gray-200 dark:border-slate-700/60 flex flex-col">
          <div class="px-6 py-4 border-b border-gray-200 dark:border-slate-700/50 flex justify-between items-center bg-gray-50 dark:bg-slate-800/50">
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ rule ? 'Редактировать правило' : 'Новое правило' }}
            </h3>
            <button @click="close" class="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-white transition-colors" :disabled="loading">
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
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Тип правила</span>
                <select
                  v-model="formData.rule_type"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  @change="setDefaultsByType(formData.rule_type)"
                  :disabled="loading"
                >
                  <option
                    v-for="option in availableRuleTypeOptions"
                    :key="option.value"
                    :value="option.value"
                  >
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

            <div class="rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-3">
              <div class="mb-2 flex items-center justify-between gap-3">
                <div class="text-xs font-semibold text-gray-600 dark:text-slate-300 uppercase">Избранные правила</div>
                <button
                  type="button"
                  class="text-xs font-medium text-teal-700 hover:text-teal-600 dark:text-teal-300 dark:hover:text-teal-200"
                  :disabled="favoriteRulesLoading || loading"
                  @click="loadFavoriteRules"
                >
                  Обновить
                </button>
              </div>
              <div v-if="favoriteRulesLoading" class="text-xs text-gray-500 dark:text-slate-400">Загружаю избранные правила...</div>
              <div v-else-if="favoriteRulesError" class="text-xs text-red-600 dark:text-red-400">{{ favoriteRulesError }}</div>
              <div v-else-if="!favoriteRules.length" class="text-xs text-gray-500 dark:text-slate-400">
                Пометьте любое правило этого направления звездочкой, и оно появится здесь.
              </div>
              <div v-else class="flex flex-wrap gap-2">
                <button
                  v-for="favorite in favoriteRules"
                  :key="favorite.id"
                  type="button"
                  class="rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors"
                  :disabled="loading"
                  @click="applyFavoriteRule(favorite)"
                >
                  ★ {{ favorite.name }}
                </button>
              </div>
            </div>

            <div class="rounded-lg border border-sky-200 dark:border-sky-500/40 bg-sky-50 dark:bg-sky-900/20 px-3 py-2">
              <div class="text-xs font-semibold text-sky-700 dark:text-sky-300">
                Как работает: {{ selectedRuleTypeOption?.label }}
              </div>
              <div class="text-xs text-sky-700/90 dark:text-sky-200 mt-1">
                {{ selectedRuleTypeOption?.description }}
              </div>
              <div class="text-xs text-sky-700/90 dark:text-sky-200 mt-1">
                {{ selectedRuleTypeOption?.formula }}
              </div>
            </div>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Название *</span>
              <input
                v-model="formData.name"
                type="text"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                :disabled="loading"
              />
            </label>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Шаблон строки</span>
              <input
                ref="lineTemplateInput"
                v-model="formData.line_template"
                type="text"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                :disabled="loading"
              />
              <div class="mt-2">
                <div class="text-xs text-gray-500 dark:text-slate-400 mb-2">
                  Клик по плейсхолдеру вставляет его в шаблон по курсору и копирует в буфер.
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="item in displayedPlaceholderHints"
                    :key="item.token"
                    type="button"
                    class="px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-xs text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors"
                    :disabled="loading"
                    @click="insertPlaceholder(item.token)"
                  >
                    {{ item.token }}
                  </button>
                </div>
                <div class="mt-2 text-xs text-emerald-600 dark:text-emerald-400 min-h-[18px]">
                  {{ hint }}
                </div>
                <div class="mt-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-2 space-y-1">
                  <div
                    v-for="item in displayedPlaceholderHints"
                    :key="`hint-${item.token}`"
                    class="text-xs text-gray-600 dark:text-slate-300"
                  >
                    <span class="font-semibold text-gray-800 dark:text-slate-100">{{ item.token }}</span>
                    — {{ item.title }}: {{ item.description }}
                  </div>
                </div>
              </div>
            </label>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Ед. измерения</span>
                <input
                  v-model="formData.unit"
                  type="text"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>
              <label class="block">
                <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Цена за единицу (BYN)</span>
                <input
                  v-model.number="formData.unit_price"
                  type="number"
                  min="0"
                  step="0.01"
                  class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>
            </div>

            <label class="block">
              <span class="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Service ID (опционально)</span>
              <input
                v-model.number="formData.service_id"
                type="number"
                min="1"
                class="w-full bg-white dark:bg-slate-900 border border-gray-300 dark:border-slate-600 rounded-lg px-3 py-2 text-gray-900 dark:text-slate-200"
                :disabled="loading"
              />
            </label>

            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <label class="inline-flex items-center gap-2">
                <input v-model="formData.is_optional" type="checkbox" class="h-4 w-4" :disabled="loading" />
                <span class="text-sm text-gray-700 dark:text-slate-300">Опциональное</span>
              </label>
              <label class="inline-flex items-center gap-2">
                <input v-model="formData.is_favorite" type="checkbox" class="h-4 w-4" :disabled="loading" />
                <span class="text-sm text-gray-700 dark:text-slate-300">В избранное</span>
              </label>
              <label class="inline-flex items-center gap-2">
                <input v-model="formData.is_active" type="checkbox" class="h-4 w-4" :disabled="loading" />
                <span class="text-sm text-gray-700 dark:text-slate-300">Активно</span>
              </label>
            </div>
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
              :disabled="loading || !String(formData.name || '').trim()"
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
