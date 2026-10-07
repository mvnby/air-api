<script setup lang="ts">
import OrderMoney from './OrderMoney.vue';
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import type { ManagerQuickTariffResponse, ManagerTariffServiceKind } from '../../client';
import { api } from '../../api';
import { getApiErrorMessage } from '../../utils/api-errors';
import { orderedServiceKinds, preferredServiceKind } from './service-catalog-order';
import type { OrderWorkflowType } from './order-workspace';
import { standardServiceChoice, type SuggestedInstallation } from './service-installation-choices';

const props = defineProps<{
  workflow: OrderWorkflowType;
  autofocus?: boolean;
  suggestions?: SuggestedInstallation[];
}>();
const title = defineModel<string>({ required: true });
const emit = defineEmits<{
  focus: []; input: []; blur: [];
  select: [choice: ManagerQuickTariffResponse, quantity?: number];
  addSuggested: [];
}>();
const container = ref<HTMLElement | null>(null);
const field = ref<HTMLTextAreaElement | null>(null);
const open = ref(false);
// Undefined follows the workflow for an empty row and searches all kinds for text.
// Null is the manager's explicit choice to search all categories.
const kind = ref<ManagerTariffServiceKind | null | undefined>(undefined);
const activeKind = computed(() => kind.value === undefined
  ? (title.value.trim() ? null : preferredServiceKind(props.workflow))
  : kind.value);
const browsingCategory = ref(false);
const options = ref<ManagerQuickTariffResponse[]>([]);
const loading = ref(false);
const error = ref('');
const highlighted = ref(-1);
const kinds = computed(() => orderedServiceKinds(props.workflow));
let request = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const load = async () => {
  const attempt = ++request;
  const query = browsingCategory.value ? '' : title.value.trim();
  loading.value = true;
  options.value = [];
  highlighted.value = -1;
  error.value = '';
  try {
    const response = await api.listManagerQuickTariffs(query, activeKind.value, 100);
    if (attempt !== request) return;
    options.value = response.items;
    highlighted.value = -1;
  } catch (failure) {
    if (attempt !== request) return;
    options.value = [];
    error.value = getApiErrorMessage(failure);
  } finally { if (attempt === request) loading.value = false; }
};
const focus = () => {
  if (!open.value) { open.value = true; void load(); }
  emit('focus');
};
const input = () => {
  open.value = true;
  browsingCategory.value = false;
  emit('input');
  clearTimeout(timer);
  // Invalidate the response for the previous text immediately.
  request += 1;
  options.value = [];
  timer = setTimeout(() => void load(), 200);
};
const selectKind = (value: ManagerTariffServiceKind) => {
  kind.value = activeKind.value === value ? null : value;
  // Browse a section even when the manager's current text matches no template.
  // Their text stays in the row; further typing searches this section.
  browsingCategory.value = kind.value !== null;
  clearTimeout(timer);
  void load();
};
const choose = (option: ManagerQuickTariffResponse, quantity?: number) => {
  request += 1;
  clearTimeout(timer);
  open.value = false;
  loading.value = false;
  emit('select', option, quantity);
};
const focusOut = (event: FocusEvent) => {
  if (event.relatedTarget instanceof Node && container.value?.contains(event.relatedTarget)) return;
  open.value = false;
  request += 1;
  clearTimeout(timer);
  emit('blur');
};
const keydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    open.value = false;
    request += 1;
    clearTimeout(timer);
    loading.value = false;
    event.preventDefault();
    return;
  }
  if (!open.value) return;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    highlighted.value = Math.max(0, Math.min(options.value.length - 1,
      highlighted.value + (event.key === 'ArrowDown' ? 1 : -1)));
  } else if (event.key === 'Enter' && !event.shiftKey && highlighted.value >= 0) {
    event.preventDefault();
    const option = options.value[highlighted.value];
    if (option) choose(option);
  }
};
watch(() => props.autofocus, async (autofocus) => {
  if (autofocus) { await nextTick(); field.value?.focus({ preventScroll: true }); }
}, { immediate: true });
watch(() => props.workflow, () => {
  clearTimeout(timer);
  if (open.value) void load();
});
onBeforeUnmount(() => { request += 1; clearTimeout(timer); });
</script>

<template>
  <div ref="container" class="min-w-0" @focusout="focusOut">
    <textarea ref="field" v-model="title" data-testid="service-title-input" data-order-usage="order_service_edit" class="field-input min-h-[64px] resize-y text-sm leading-snug [field-sizing:content]" rows="2" placeholder="Название услуги — можно написать своё" aria-label="Название услуги" :aria-expanded="open" aria-autocomplete="list" @focus="focus" @click="focus" @input="input" @keydown="keydown" />
    <div v-if="open" data-testid="service-context-menu" class="mt-1 min-w-0 rounded-lg border border-slate-200 bg-white p-2 shadow-sm dark:border-slate-700 dark:bg-slate-950">
      <div class="flex flex-wrap gap-1" role="group" aria-label="Разделы услуг">
        <button v-for="item in kinds" :key="item.value" type="button" class="min-h-8 rounded-lg px-2 text-xs font-medium" :class="activeKind === item.value ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" :aria-pressed="activeKind === item.value" @mousedown.prevent @click="selectKind(item.value)">{{ item.label }}</button>
      </div>
      <div class="mt-2 max-h-72 space-y-1 overflow-y-auto" aria-label="Подсказки услуг">
        <div v-if="suggestions?.length && !title.trim() && activeKind === 'installation'" class="border-b border-slate-100 pb-2">
          <p class="px-2 text-[11px] text-slate-500">Для оборудования в предложении</p>
          <button v-for="group in suggestions" :key="group.tariff.code" type="button" class="block w-full rounded-lg px-2 py-2 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800" @mousedown.prevent @click="choose(standardServiceChoice(group.tariff), group.quantity)">
            <span class="block font-medium text-slate-900 dark:text-slate-100">{{ group.tariff.title }}</span>
            <span class="text-slate-500 dark:text-slate-400">{{ group.quantity }} шт. × <OrderMoney :value="Number(group.tariff.price)" /></span>
          </button>
          <button v-if="suggestions.length > 1" type="button" data-testid="add-all-suggested-installations" class="min-h-8 px-2 text-xs font-medium text-brand-700" @mousedown.prevent @click="open = false; emit('addSuggested')">Добавить все предложенные монтажи</button>
        </div>
        <p v-if="loading" class="px-2 py-2 text-xs text-slate-500">Ищем услуги…</p>
        <p v-else-if="error" class="px-2 py-2 text-xs text-slate-500" role="status">Подсказки не загрузились. Можно заполнить услугу вручную. <button type="button" class="underline" @mousedown.prevent @click="load">Повторить</button></p>
        <button v-for="(option, index) in options" :key="option.installation_standard?.code || option.tariff_id || index" type="button" :data-testid="`select-service-${option.installation_standard?.code || option.tariff_id}`" class="block w-full rounded-lg px-2 py-2 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-800" :class="highlighted === index ? 'bg-brand-50 dark:bg-slate-800' : ''" @mousedown.prevent @click="choose(option)">
          <span class="block font-medium text-slate-900 dark:text-slate-100">{{ option.short_name || option.title }}</span>
          <span v-if="option.full_description" class="mt-0.5 block line-clamp-2 text-[11px] leading-snug text-slate-500">{{ option.full_description }}</span>
          <span class="mt-1 block text-slate-600 dark:text-slate-300"><OrderMoney :value="Number(option.price)" /></span>
        </button>
        <p v-if="!loading && !error && !options.length" class="px-2 py-2 text-xs text-slate-500">Подходящих услуг нет. Оставьте своё название и укажите цену.</p>
      </div>
    </div>
  </div>
</template>
