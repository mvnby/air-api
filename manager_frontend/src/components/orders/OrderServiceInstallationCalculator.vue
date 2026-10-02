<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ManagerInstallationEstimatesService, type ManagerInstallationPreviewResponse, type ManagerInstallationStandardTariff, type ManagerInstallationPreviewPayload } from '../../client';
import { listInstallationStandardTariffs, installationStandardWork, type StandardInstallationChoice } from '../../services/installation-estimate-api';
import { getApiErrorMessage } from '../../utils/api-errors';
import { formatMoney } from './order-utils';

const props = defineProps<{ initialTariff?: ManagerInstallationStandardTariff | null; quantity: number }>();
const emit = defineEmits<{ close: []; apply: [line: { title: string; description: string; price: number; installation_standard: ManagerInstallationStandardTariff }] }>();
const tariffs = ref<StandardInstallationChoice[]>([]);
const selectedCode = ref('');
const selected = computed(() => tariffs.value.find((item) => item.code === selectedCode.value));
const loading = ref(true);
const busy = ref(false);
const error = ref('');
const route = ref(3);
const thick = ref(1);
const thin = ref(0);
const over80 = ref(0);
const chase = ref(0);
const pump = ref(false);
const preview = ref<ManagerInstallationPreviewResponse | null>(null);
let epoch = 0;
let disposed = false;
const reset = () => {
  epoch += 1;
  busy.value = false;
  preview.value = null;
  error.value = '';
  pump.value = false;
  chase.value = 0;
  if (!selected.value) return;
  try {
    const base = installationStandardWork({ status: 'fixed', scope_ref: '', included: {
      route_m: selected.value.route_m, holes_by_type: selected.value.holes_by_type,
    } });
    route.value = base.route;
    thick.value = base.thick;
    thin.value = base.thin;
    over80.value = base.over80;
  } catch (failure) { error.value = getApiErrorMessage(failure); }
};
watch(selectedCode, reset);
watch([route, thick, thin, over80, chase, pump], () => { epoch += 1; busy.value = false; preview.value = null; });
const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await listInstallationStandardTariffs();
    if (disposed) return;
    tariffs.value = response.items;
    selectedCode.value = props.initialTariff && response.items.some((item) => item.code === props.initialTariff?.code)
      ? props.initialTariff.code : '';
  } catch (failure) { if (!disposed) error.value = getApiErrorMessage(failure); }
  finally { if (!disposed) loading.value = false; }
};
const calculate = async () => {
  const tariff = selected.value;
  if (!tariff || busy.value) return;
  error.value = '';
  preview.value = null;
  if (!Number.isFinite(route.value) || route.value < 0 || route.value > 1000 ||
      !Number.isFinite(chase.value) || chase.value < 0 || chase.value > 1000 ||
      [thin.value, thick.value, over80.value].some((value) => !Number.isInteger(value) || value < 0 || value > 100)) {
    error.value = 'Проверьте длину трассы и количество проходов.';
    return;
  }
  const attempt = ++epoch;
  busy.value = true;
  const key = 'service-row';
  const payload: ManagerInstallationPreviewPayload = {
    expected_revision: tariff.bookRevision,
    tariff_selections: { [key]: tariff.code },
    installations: [{
      key, display_label: 'Монтаж', work_kind: 'standard',
      typed_profile: { product_kind: tariff.product_kind, indoor_type: tariff.indoor_type as any, confirmed: true },
      route_length_m: route.value,
      holes_by_type: { through_thin: thin.value, through_thick: thick.value, through_over_80: over80.value },
      extras: [
        ...(pump.value ? [{ code: 'pump.package', quantity: 1 }] : []),
        ...(chase.value > 0 ? [{ code: 'chase.extra_m', quantity: chase.value }] : []),
      ],
    }],
  };
  try {
    const response = await ManagerInstallationEstimatesService.previewManagerInstallationEstimate(crypto.randomUUID(), payload);
    if (!disposed && attempt === epoch) preview.value = response;
  } catch (failure) { if (!disposed && attempt === epoch) error.value = getApiErrorMessage(failure); }
  finally { if (!disposed && attempt === epoch) busy.value = false; }
};
const resultLine = computed(() => {
  if (preview.value?.status !== 'fixed' || !selected.value) return null;
  const lines = preview.value.collapsed_lines || [];
  return {
    title: selected.value.title,
    description: lines.map((line) => line.description || line.title).join('; ') || selected.value.description,
    price: Number(preview.value.total),
    installation_standard: selected.value,
  };
});
const apply = () => { if (resultLine.value) emit('apply', resultLine.value); };
onMounted(load);
onBeforeUnmount(() => { disposed = true; epoch += 1; });
</script>

<template>
  <div class="mt-3 min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid="service-installation-calculator">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-sm font-medium text-slate-900">Рассчитать монтаж</p>
      <button type="button" class="btn-mini-outline min-h-8 text-xs" @click="emit('close')">Закрыть расчёт</button>
    </div>
    <p class="mt-1 text-xs text-slate-500">Расчёт на один монтаж. Количество в строке — {{ quantity }}. Название, описание и цена изменятся только после применения.</p>
    <p v-if="loading" class="mt-2 text-xs text-slate-500">Загружаем опубликованные тарифы…</p>
    <template v-else>
      <label class="mt-3 block text-xs text-slate-600">Стандартный тариф
        <select v-model="selectedCode" data-testid="calculator-tariff" class="field-input mt-1"><option value="">Выберите тип и мощность</option><option v-for="tariff in tariffs" :key="tariff.code" :value="tariff.code">{{ tariff.title }} · {{ formatMoney(Number(tariff.price)) }}</option></select>
      </label>
      <p v-if="!tariffs.length && !error" class="mt-2 text-xs text-slate-600">Нет опубликованных стандартных тарифов. Название и цену услуги можно указать вручную.</p>
      <div v-if="selected" class="mt-3 space-y-3">
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="text-xs text-slate-600">Трасса на один монтаж, м<input v-model.number="route" data-testid="calculator-route" type="number" min="0" max="1000" step="0.01" class="field-input mt-1" /></label>
          <label class="text-xs text-slate-600">Проходы стены до 80 см, шт.<input v-model.number="thick" data-testid="calculator-thick" type="number" min="0" max="100" step="1" class="field-input mt-1" /></label>
        </div>
        <label class="flex items-center gap-2 text-xs"><input v-model="pump" type="checkbox" data-testid="calculator-pump" />Дренажный насос с установкой</label>
        <details class="rounded-md border border-slate-200 bg-white p-2">
          <summary class="cursor-pointer text-xs text-slate-600">Дополнительные проходы и штробление</summary>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="text-xs text-slate-600">Межкомнатные проходы до 20 см, шт.<input v-model.number="thin" type="number" min="0" max="100" step="1" class="field-input mt-1" /></label>
            <label class="text-xs text-slate-600">Проходы свыше 80 см, шт.<input v-model.number="over80" type="number" min="0" max="100" step="1" class="field-input mt-1" /><span class="block text-[11px]">Потребуют отдельной оценки</span></label>
            <label class="text-xs text-slate-600">Штробление, м<input v-model.number="chase" type="number" min="0" max="1000" step="0.01" class="field-input mt-1" /></label>
          </div>
        </details>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn-mini min-h-8 text-xs" :disabled="busy" data-testid="calculator-calculate" @click="calculate">{{ busy ? 'Считаем…' : 'Рассчитать по тарифу' }}</button>
          <button type="button" class="btn-mini-outline min-h-8 text-xs" @click="reset">Сбросить к стандартному составу</button>
        </div>
      </div>
    </template>
    <p v-if="error" role="alert" class="mt-2 text-xs text-red-700">{{ error }}</p>
    <div v-if="preview" class="mt-3 border-t border-slate-200 pt-3">
      <template v-if="resultLine">
        <p class="text-sm font-semibold">{{ formatMoney(resultLine.price) }} за монтаж · {{ formatMoney(resultLine.price * quantity) }} за {{ quantity }} шт.</p>
        <p class="mt-1 text-xs leading-relaxed text-slate-600">{{ resultLine.description }}</p>
        <button type="button" class="btn-mini mt-3 min-h-8 text-xs" data-testid="calculator-apply" @click="apply">Применить к строке</button>
      </template>
      <p v-else class="text-xs text-slate-600" role="status">{{ preview.status === 'quote' ? 'Для этого состава нужна отдельная оценка. Можно указать согласованную цену вручную.' : 'Точной цены по тарифу нет. Можно указать согласованную цену вручную.' }}</p>
    </div>
  </div>
</template>
