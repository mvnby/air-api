<script setup lang="ts">
import { computed } from 'vue';
import {
  type ConsumerDocumentTerms,
  isRouteLayingDocumentType,
  isSupplyInstallationDocumentType,
} from '../model/consumer-document-terms';

const props = defineProps<{
  documentType: string;
  terms: ConsumerDocumentTerms;
}>();

const emit = defineEmits<{
  updateTerms: [terms: ConsumerDocumentTerms];
}>();

const isRouteLaying = computed(() => isRouteLayingDocumentType(props.documentType));
const isSupplyInstallation = computed(() => isSupplyInstallationDocumentType(props.documentType));

const update = (changes: Partial<ConsumerDocumentTerms>) => {
  emit('updateTerms', { ...props.terms, ...changes });
};

const updateText = (field: keyof ConsumerDocumentTerms, event: Event) => {
  const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value.trim();
  update({ [field]: value || null } as Partial<ConsumerDocumentTerms>);
};

const updateMonths = (field: 'goods_warranty_months' | 'work_warranty_months', event: Event) => {
  const rawValue = (event.target as HTMLInputElement).value;
  const value = rawValue === '' ? null : Number(rawValue);
  update({ [field]: Number.isFinite(value) ? value : null } as Partial<ConsumerDocumentTerms>);
};
</script>

<template>
  <section class="mt-4 rounded-xl border border-teal-200 bg-teal-50/70 p-4 dark:border-teal-900/70 dark:bg-teal-950/20" data-testid="consumer-document-terms">
    <div>
      <h4 class="text-sm font-bold text-teal-950 dark:text-teal-100">Данные для документа физлицу</h4>
      <p class="mt-1 text-xs leading-5 text-teal-900/75 dark:text-teal-200/75">Эти данные попадут в снимок черновика и не изменятся вслед за карточкой заказа.</p>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label class="consumer-field"><span>Бренд оборудования</span><input :value="terms.equipment_brand || ''" class="consumer-input" data-testid="consumer-equipment-brand" placeholder="Например, Midea" @input="updateText('equipment_brand', $event)" /></label>
      <label class="consumer-field"><span>Модель</span><input :value="terms.equipment_model || ''" class="consumer-input" placeholder="MSAG-09HRN1" @input="updateText('equipment_model', $event)" /></label>
      <label class="consumer-field"><span>Серийный номер</span><input :value="terms.equipment_serial || ''" class="consumer-input" @input="updateText('equipment_serial', $event)" /></label>
      <label v-if="isSupplyInstallation" class="consumer-field"><span>Гарантия на оборудование, мес.</span><input :value="terms.goods_warranty_months ?? ''" class="consumer-input" data-testid="consumer-goods-warranty" type="number" min="0" max="240" @input="updateMonths('goods_warranty_months', $event)" /></label>
      <label v-if="isSupplyInstallation" class="consumer-field sm:col-span-2"><span>Условия гарантии на оборудование</span><input :value="terms.goods_warranty_terms || ''" class="consumer-input" placeholder="Например, при соблюдении правил эксплуатации" @input="updateText('goods_warranty_terms', $event)" /></label>
      <label class="consumer-field"><span>Гарантия на работы, мес.</span><input :value="terms.work_warranty_months ?? ''" class="consumer-input" type="number" min="0" max="240" placeholder="Если предусмотрена" @input="updateMonths('work_warranty_months', $event)" /></label>
      <label class="consumer-field sm:col-span-2"><span>Условия гарантии на работы</span><input :value="terms.work_warranty_terms || ''" class="consumer-input" placeholder="Дополнительные условия, если есть" @input="updateText('work_warranty_terms', $event)" /></label>
    </div>

    <template v-if="isRouteLaying">
      <div class="mt-5 border-t border-teal-200 pt-4 dark:border-teal-900/70">
        <h5 class="text-sm font-bold text-teal-950 dark:text-teal-100">Параметры закладки трассы</h5>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label class="consumer-field"><span>Длина, м</span><input :value="terms.route_length_meters || ''" class="consumer-input" inputmode="decimal" @input="updateText('route_length_meters', $event)" /></label>
          <label class="consumer-field"><span>Жидкостная труба, мм</span><input :value="terms.route_liquid_pipe_diameter_mm || ''" class="consumer-input" inputmode="decimal" @input="updateText('route_liquid_pipe_diameter_mm', $event)" /></label>
          <label class="consumer-field"><span>Газовая труба, мм</span><input :value="terms.route_gas_pipe_diameter_mm || ''" class="consumer-input" inputmode="decimal" @input="updateText('route_gas_pipe_diameter_mm', $event)" /></label>
          <label class="consumer-field"><span>Дренаж</span><input :value="terms.route_drainage || ''" class="consumer-input" @input="updateText('route_drainage', $event)" /></label>
          <label class="consumer-field sm:col-span-2"><span>Электропитание</span><input :value="terms.route_power_supply || ''" class="consumer-input" @input="updateText('route_power_supply', $event)" /></label>
          <label class="consumer-field sm:col-span-2 lg:col-span-3"><span>Примечания</span><textarea :value="terms.route_notes || ''" class="consumer-input min-h-20 py-2" @input="updateText('route_notes', $event)" /></label>
        </div>

        <div class="mt-3 flex flex-wrap gap-2" aria-label="Контроль выполнения работ">
          <button type="button" class="consumer-toggle" :class="terms.route_photo_fixation_performed ? 'consumer-toggle-active' : 'consumer-toggle-idle'" :aria-pressed="terms.route_photo_fixation_performed" @click="update({ route_photo_fixation_performed: !terms.route_photo_fixation_performed })">Фотофиксация</button>
          <button type="button" class="consumer-toggle" :class="terms.route_pressure_test_performed ? 'consumer-toggle-active' : 'consumer-toggle-idle'" :aria-pressed="terms.route_pressure_test_performed" @click="update({ route_pressure_test_performed: !terms.route_pressure_test_performed })">Опрессовка</button>
          <button type="button" class="consumer-toggle" :class="terms.route_ends_capped ? 'consumer-toggle-active' : 'consumer-toggle-idle'" :aria-pressed="terms.route_ends_capped" @click="update({ route_ends_capped: !terms.route_ends_capped })">Концы заглушены</button>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.consumer-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-teal-950/80 dark:text-teal-100/80; }
.consumer-input { @apply h-10 w-full rounded-xl border border-teal-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 dark:border-teal-900 dark:bg-slate-900 dark:text-white; }
.consumer-toggle { @apply h-9 rounded-lg border px-3 text-sm font-semibold transition; }
.consumer-toggle-active { @apply border-teal-600 bg-teal-600 text-white; }
.consumer-toggle-idle { @apply border-teal-200 bg-white text-teal-900 hover:border-teal-400 dark:border-teal-900 dark:bg-slate-900 dark:text-teal-100; }
</style>
