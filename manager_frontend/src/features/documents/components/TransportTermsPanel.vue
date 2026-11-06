<script setup lang="ts">
import type { TransportOperation } from '../../../client';
import { handlingStages, type HandlingStage, type TransportTerms } from '../model/transport-terms';

const props = defineProps<{ terms: TransportTerms; expanded?: boolean }>();
const emit = defineEmits<{ updateTerms: [terms: TransportTerms] }>();

const vehicleFields = [
  { key: 'car_model', label: 'Автомобиль', max: 200 },
  { key: 'car_number', label: 'Регистрационный номер', max: 64 },
  { key: 'driver_name', label: 'Водитель', max: 300 },
  { key: 'carrier', label: 'Перевозчик', max: 500 },
] as const;
const routeFields = [
  { key: 'loading_point', label: 'Пункт погрузки', max: 500 },
  { key: 'unloading_point', label: 'Пункт разгрузки', max: 500 },
  { key: 'trip_sheet_number', label: 'Номер путевого листа', max: 100 },
  { key: 'freight_payer', label: 'Заказчик автоперевозки (плательщик)', max: 500 },
  { key: 'freight_payer_unp', label: 'УНП плательщика', max: 9 },
] as const;
const operationFields = [
  { key: 'performer', label: 'Исполнитель', type: 'text', max: 300 },
  { key: 'method', label: 'Способ', type: 'text', max: 200 },
  { key: 'arrived_at', label: 'Прибытие', type: 'datetime-local' },
  { key: 'departed_at', label: 'Убытие', type: 'datetime-local' },
  { key: 'downtime_minutes', label: 'Время простоя, мин', type: 'number' },
] as const;

const valueOf = (event: Event) => (event.target as HTMLInputElement).value;
const update = (field: keyof TransportTerms, event: Event) => {
  const value = valueOf(event) || null;
  const next = { ...props.terms, [field]: value };
  if (field === 'freight_payer' && value !== props.terms.freight_payer) next.freight_payer_unp = null;
  emit('updateTerms', next);
};
const updateOperation = (stage: HandlingStage, key: keyof TransportOperation, event: Event) => {
  const value = valueOf(event);
  const updated = { ...props.terms[stage], [key]: value && key === 'downtime_minutes' ? Number(value) : value || null };
  emit('updateTerms', { ...props.terms, [stage]: Object.values(updated).some(v => v != null) ? updated : null });
};
</script>

<template>
  <details :open="expanded" class="transport mt-4 min-w-0 rounded-xl border border-sky-200 bg-sky-50/60 p-3 dark:border-sky-900/70 dark:bg-sky-950/20 sm:p-4" data-testid="transport-terms-panel">
    <summary class="cursor-pointer py-1 text-sm font-bold">Транспорт и маршрут <span class="font-normal text-slate-600 dark:text-slate-300">· необязательно</span></summary>
    <div class="fields">
      <label v-for="field in vehicleFields" :key="field.key">
        <span>{{ field.label }}</span>
        <input :value="terms[field.key] || ''" :maxlength="field.max" @input="update(field.key, $event)" />
      </label>
    </div>
    <h5 class="mt-4 text-sm font-bold">Маршрут</h5>
    <div class="fields">
      <label v-for="field in routeFields" :key="field.key">
        <span>{{ field.label }}</span>
        <textarea v-if="field.key === 'loading_point' || field.key === 'unloading_point' || field.key === 'freight_payer'"
          :value="terms[field.key] || ''" :maxlength="field.max" rows="2" @input="update(field.key, $event)" />
        <input v-else :value="terms[field.key] || ''" :maxlength="field.max"
          :inputmode="field.key === 'freight_payer_unp' ? 'numeric' : undefined" @input="update(field.key, $event)" />
      </label>
    </div>
    <div class="mt-3 grid min-w-0 gap-2">
      <details v-for="stage in handlingStages" :key="stage.key" class="min-w-0 rounded-lg border border-sky-200 p-2.5 dark:border-sky-900" :data-testid="`ttn-${stage.key}-operation`">
        <summary class="cursor-pointer py-1 text-sm font-semibold">{{ stage.label }}</summary>
        <div class="fields">
          <label v-for="field in operationFields" :key="field.key">
            <span>{{ field.label }}</span>
            <input :type="field.type" :value="terms[stage.key]?.[field.key] ?? ''" :maxlength="'max' in field ? field.max : undefined"
              :min="field.type === 'number' ? 0 : undefined" :step="field.type === 'number' ? 1 : undefined"
              @input="updateOperation(stage.key, field.key, $event)" />
          </label>
        </div>
      </details>
    </div>
    <p v-if="!terms.car_number || !terms.driver_name || !terms.carrier" class="mt-3 text-xs font-semibold text-amber-700 dark:text-amber-300">
      Перед выпуском проверьте номер автомобиля, водителя и перевозчика.
    </p>
  </details>
</template>

<style scoped>
.fields { @apply mt-2 grid min-w-0 gap-3 md:grid-cols-2; }
.transport label { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.transport input, .transport textarea { @apply box-border h-11 min-w-0 w-full max-w-full rounded-lg border border-slate-300 bg-white px-2 text-sm font-normal text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
.transport textarea { @apply h-auto resize-y py-2; }
</style>
