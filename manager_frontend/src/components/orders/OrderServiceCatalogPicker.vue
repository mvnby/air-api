<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../../api';
import type { ManagerInstallEstimateResponse, ManagerOrderServiceLinePayload, ManagerQuickTariffResponse, ManagerTariffResponse, ManagerTariffRuleResponse, ManagerTariffServiceKind } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import type { OrderWorkflowType } from './order-workspace';
import { orderedServiceKinds, preferredServiceKind, serviceCategories } from './service-catalog-order';
import { formatMoney } from './order-utils';

const props = defineProps<{ workflow: OrderWorkflowType; customerId?: number | null }>();
const emit = defineEmits<{
  choose: [tariff: ManagerQuickTariffResponse];
  custom: [];
  createdEstimate: [payload: { id: number; lines: ManagerOrderServiceLinePayload[] }];
  close: [];
}>();

const tariffs = ref<ManagerTariffResponse[]>([]);
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const kind = ref<ManagerTariffServiceKind>(preferredServiceKind(props.workflow));
const category = ref('');
const query = ref('');
const selectedTariff = ref<ManagerTariffResponse | null>(null);
const routeLength = ref(0);
const quantity = ref(1);
const extraHoles = ref(0);
const discount = ref(0);
const ruleInputs = ref<Record<number, number>>({});
const calculation = ref<ManagerInstallEstimateResponse | null>(null);
const kinds = computed(() => orderedServiceKinds(props.workflow));
const categories = computed(() => serviceCategories(tariffs.value, kind.value));
const visibleTariffs = computed(() => tariffs.value.filter((tariff) => (
  tariff.service_kind === kind.value
  && (!category.value || tariff.category.trim() === category.value)
  && (!query.value.trim() || [tariff.short_name, tariff.full_description, tariff.category, tariff.power_range]
    .some((value) => String(value || '').toLocaleLowerCase('ru').includes(query.value.trim().toLocaleLowerCase('ru'))))
)));
const manualRules = computed(() => (selectedTariff.value?.rules || []).filter((rule) => (
  rule.is_active && (rule.rule_type === 'per_unit_manual' || (rule.rule_type === 'fixed_once' && rule.is_optional))
)));
const hasRule = (type: string) => (selectedTariff.value?.rules || []).some((rule) => rule.is_active && rule.rule_type === type);

watch(() => props.workflow, (workflow) => { kind.value = preferredServiceKind(workflow); });
watch(kind, () => { category.value = ''; selectedTariff.value = null; });
watch([routeLength, quantity, extraHoles, discount, ruleInputs], () => { calculation.value = null; }, { deep: true });

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await api.listManagerTariffsByKind(undefined, false);
    tariffs.value = response.items.filter((tariff) => tariff.is_active);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};

const choose = (tariff: ManagerTariffResponse) => {
  emit('choose', {
    tariff_id: tariff.id,
    service_kind: tariff.service_kind,
    short_name: tariff.short_name || tariff.selector_label,
    full_description: tariff.full_description || null,
    title: tariff.short_name || tariff.selector_label,
    price: tariff.base_price,
    category: tariff.category,
    power_range: tariff.power_range,
    included_route_meters: tariff.included_route_meters,
  });
};

const startEstimate = (tariff: ManagerTariffResponse) => {
  selectedTariff.value = tariff;
  routeLength.value = tariff.included_route_meters;
  quantity.value = 1;
  extraHoles.value = 0;
  discount.value = 0;
  ruleInputs.value = {};
  calculation.value = null;
  error.value = '';
};

const ruleQuantity = (rule: ManagerTariffRuleResponse) => Number(ruleInputs.value[rule.id] || 0);
const payload = () => ({
  tariff_id: selectedTariff.value!.id,
  route_length_m: Math.max(0, Number(routeLength.value) || 0),
  quantity: Math.max(1, Math.trunc(Number(quantity.value) || 1)),
  extra_holes_count: Math.max(0, Math.trunc(Number(extraHoles.value) || 0)),
  discount_amount: Math.max(0, Number(discount.value) || 0),
  rule_inputs: manualRules.value.map((rule) => ({ rule_id: rule.id, qty: ruleQuantity(rule) })).filter((input) => input.qty > 0),
});

const calculate = async () => {
  if (!selectedTariff.value) return;
  busy.value = true;
  error.value = '';
  try {
    calculation.value = await api.calculateManagerInstallEstimate(payload());
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    busy.value = false;
  }
};

const saveAndAdd = async () => {
  if (!selectedTariff.value || !calculation.value) return;
  busy.value = true;
  error.value = '';
  try {
    const estimate = await api.createManagerServiceEstimate({
      ...payload(),
      title: selectedTariff.value.short_name || selectedTariff.value.selector_label,
      customer_id: props.customerId || null,
      status: 'draft',
    });
    const orderLines = await api.getManagerServiceEstimateOrderLines(estimate.id, 'detailed', 'short');
    if (!orderLines.services.length) throw new Error('Смета сохранена, но в ней нет строк для заказа. Найдите её в готовых сметах.');
    emit('createdEstimate', { id: estimate.id, lines: orderLines.services });
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    busy.value = false;
  }
};

onMounted(load);
</script>

<template>
  <div class="mt-3 rounded-xl border border-brand-200 bg-brand-50/50 p-3" data-testid="service-catalog-picker">
    <div class="flex items-center justify-between gap-2">
      <h5 class="text-sm font-semibold text-slate-900">Подобрать услугу</h5>
      <button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="emit('close')">Закрыть</button>
    </div>
    <p class="mt-1 text-xs text-slate-500">Выберите тариф для услуги или соберите смету с дополнительными работами.</p>
    <p v-if="error" class="mt-2 text-xs text-red-700" role="alert">{{ error }}</p>
    <template v-if="selectedTariff">
      <div class="mt-3 flex items-start justify-between gap-3">
        <div><p class="text-sm font-semibold">{{ selectedTariff.short_name }}</p><p class="text-xs text-slate-500">{{ selectedTariff.category }}</p></div>
        <button type="button" class="text-xs font-semibold text-brand-700" @click="selectedTariff = null">К выбору услуг</button>
      </div>
      <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <label v-if="hasRule('per_meter_over_included')" class="text-xs">Длина трассы, м<input v-model.number="routeLength" type="number" min="0" step="0.1" class="field-input mt-1" /></label>
        <label class="text-xs">Количество<input v-model.number="quantity" type="number" min="1" step="1" class="field-input mt-1" /></label>
        <label v-if="hasRule('per_hole_manual')" class="text-xs">Доп. отверстия<input v-model.number="extraHoles" type="number" min="0" step="1" class="field-input mt-1" /></label>
        <label class="text-xs">Скидка, BYN<input v-model.number="discount" type="number" min="0" step="0.01" class="field-input mt-1" /></label>
      </div>
      <div v-if="manualRules.length" class="mt-3 grid gap-2 sm:grid-cols-2">
        <label v-for="rule in manualRules" :key="rule.id" class="text-xs">{{ rule.name }} · {{ formatMoney(rule.unit_price) }} BYN/{{ rule.unit }}
          <input v-model.number="ruleInputs[rule.id]" type="number" min="0" :step="rule.rule_type === 'fixed_once' ? 1 : 0.1" class="field-input mt-1" />
        </label>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" class="btn-mini" :disabled="busy" @click="calculate">{{ busy ? 'Считаю…' : 'Рассчитать смету' }}</button>
        <span v-if="calculation" class="text-sm font-semibold">{{ formatMoney(calculation.total) }} {{ calculation.currency }}</span>
      </div>
      <ul v-if="calculation" class="mt-2 list-inside list-disc text-xs text-slate-600"><li v-for="(line, index) in calculation.lines" :key="index">{{ line.name }} · {{ formatMoney(line.line_total) }} BYN</li></ul>
      <button v-if="calculation" type="button" class="btn-mini mt-3" :disabled="busy" @click="saveAndAdd">Сохранить смету и добавить в заказ</button>
    </template>
    <template v-else>
      <div class="mt-3 flex flex-wrap gap-2" role="group" aria-label="Тип услуги">
        <button v-for="option in kinds" :key="option.value" type="button" class="rounded-lg border px-2.5 py-1.5 text-xs font-semibold" :class="kind === option.value ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-200 bg-white text-slate-700'" @click="kind = option.value">{{ option.label }}</button>
      </div>
      <input v-model="query" class="field-input mt-3" placeholder="Поиск по услугам" aria-label="Поиск по услугам" />
      <div v-if="categories.length" class="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Категория услуг">
        <button type="button" class="rounded-lg px-2 py-1 text-xs" :class="!category ? 'bg-slate-800 text-white' : 'bg-white text-slate-700'" @click="category = ''">Все</button>
        <button v-for="item in categories" :key="item" type="button" class="rounded-lg px-2 py-1 text-xs" :class="category === item ? 'bg-slate-800 text-white' : 'bg-white text-slate-700'" @click="category = item">{{ item }}</button>
      </div>
      <p v-if="loading" class="mt-3 text-xs text-slate-500">Загружаю услуги…</p>
      <div v-else class="mt-3 max-h-80 space-y-2 overflow-y-auto">
        <div v-for="tariff in visibleTariffs" :key="tariff.id" class="rounded-lg border border-slate-200 bg-white p-2.5">
          <p class="text-sm font-semibold text-slate-900">{{ tariff.short_name || tariff.selector_label }}</p>
          <p v-if="tariff.full_description" class="mt-0.5 line-clamp-2 text-xs text-slate-500">{{ tariff.full_description }}</p>
          <div class="mt-2 flex flex-wrap items-center gap-2 text-xs"><span>{{ formatMoney(tariff.base_price) }} BYN</span><span v-if="tariff.power_range">· {{ tariff.power_range }}</span></div>
          <div class="mt-2 flex gap-2"><button type="button" class="btn-mini h-8 px-2 text-xs" @click="choose(tariff)">Добавить</button><button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="startEstimate(tariff)">Собрать смету</button></div>
        </div>
        <p v-if="!visibleTariffs.length" class="text-xs text-slate-500">По этому запросу услуг нет.</p>
      </div>
      <button type="button" class="mt-3 text-xs font-semibold text-brand-700" @click="emit('custom')">Добавить свою услугу вручную</button>
    </template>
  </div>
</template>
