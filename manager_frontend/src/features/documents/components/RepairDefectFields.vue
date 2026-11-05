<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ManagerEquipmentLinksService, type ManagerOrderDetailResponse } from '../../../client';
import { equipmentIdentifiers, equipmentSubtitle, equipmentTitle } from '../../../components/equipment/registry';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { newRepairDefectForm, repairOrderSuggestions, repairVerdicts, type RepairDefectForm } from '../model/repair-defect';

const props = defineProps<{ terms: RepairDefectForm; order?: ManagerOrderDetailResponse }>();
const emit = defineEmits<{ updateTerms: [terms: RepairDefectForm] }>();
const update = (fields: Partial<RepairDefectForm>) => emit('updateTerms', { ...props.terms, ...fields });
const suggestions = computed(() => repairOrderSuggestions(props.order));
const equipmentOptions = ref<string[]>([]);
const equipmentLoading = ref(false);
const equipmentError = ref('');
const retry = ref(0);
const manualEquipment = ref(false);
let changedEquipment = false;
watch([() => props.order?.id, () => props.order?.customer?.id], () => {
  manualEquipment.value = false;
  changedEquipment = false;
}, { flush: 'sync' });
watch([() => props.order?.id, () => props.order?.customer?.id, () => props.order?.linked_equipment_count, retry], async ([orderId, customerId, count], _, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  equipmentOptions.value = [];
  equipmentError.value = '';
  equipmentLoading.value = false;
  if (!orderId || !customerId || !count) return;
  equipmentLoading.value = true;
  try {
    const response = await ManagerEquipmentLinksService.listManagerOrderEquipmentLinks(orderId);
    if (!current) return;
    const items = response.items || [];
    const names = items.filter(({ equipment }) => equipment.customer_id === customerId).map(({ equipment }) => {
      const name = equipmentTitle(equipment);
      return [name, equipmentSubtitle(equipment), equipmentIdentifiers(equipment)].filter(Boolean).join(' · ');
    });
    equipmentOptions.value = [...new Set(names)];
    if (!changedEquipment && !props.terms.equipment && items.length === 1 && names[0] && names[0].length <= 250)
      update({ equipment: names[0] });
  } catch (error) {
    if (current) equipmentError.value = getApiErrorMessage(error);
  } finally {
    if (current) equipmentLoading.value = false;
  }
}, { immediate: true });
const equipmentSelection = computed(() => !manualEquipment.value && equipmentOptions.value.includes(props.terms.equipment)
  ? props.terms.equipment : (manualEquipment.value || props.terms.equipment ? '__manual' : ''));
const chooseEquipment = (event: Event) => {
  changedEquipment = true;
  const value = (event.target as HTMLSelectElement).value;
  manualEquipment.value = value === '__manual';
  const equipment = manualEquipment.value ? '' : value;
  if (props.terms.equipment && props.terms.equipment !== equipment) {
    emit('updateTerms', { ...newRepairDefectForm(), equipment });
  } else {
    update({ equipment });
  }
};
const editEquipment = (event: Event) => {
  changedEquipment = true;
  update({ equipment: (event.target as HTMLInputElement).value });
};
const valueOf = (event: Event) => (event.target as HTMLInputElement | HTMLTextAreaElement).value;
const changeVerdict = (event: Event) => {
  const verdict = valueOf(event) as RepairDefectForm['verdict'];
  update(props.terms.verdict && verdict !== props.terms.verdict ? { verdict, cost: null, term: null } : { verdict });
};
const chargeRelevant = computed(() => ['repairable', 'needs_diagnostics'].includes(props.terms.verdict));
</script>

<template>
  <section class="repair-defect-form" data-testid="repair-defect-fields" aria-label="Заключение для клиента">
    <label class="field"><span>Вывод по оборудованию</span>
      <select class="control" data-testid="repair-verdict" :value="terms.verdict" @change="changeVerdict">
        <option value="" disabled>Выберите вывод</option>
        <option v-for="option in repairVerdicts" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <div class="space-y-2">
      <label v-if="equipmentOptions.length" class="field"><span>Оборудование из заказа</span>
        <select class="control" data-testid="repair-equipment-selection" :value="equipmentSelection" @change="chooseEquipment">
          <option value="" disabled>Выберите оборудование</option>
          <option v-for="name in equipmentOptions" :key="name" :value="name">{{ name }}</option>
          <option value="__manual">Указать вручную</option>
        </select>
      </label>
      <label v-if="!equipmentOptions.length || equipmentSelection === '__manual'" class="field"><span>Оборудование для акта</span>
        <textarea class="control" rows="2" data-testid="repair-equipment" :value="terms.equipment" maxlength="250" placeholder="Модель, серийный или инвентарный номер" @input="editEquipment"></textarea>
      </label>
      <p v-if="equipmentOptions.length > 1" class="hint">Для оборудования с другим выводом создайте отдельный акт.</p>
      <p v-if="equipmentLoading" role="status" class="hint">Загружаем оборудование заказа…</p>
      <p v-else-if="equipmentError" class="hint" role="status">Список оборудования недоступен. <button type="button" class="link" @click="retry++">Повторить</button></p>
    </div>
    <div class="space-y-1">
      <label class="field"><span>Что установлено</span>
        <textarea class="control" rows="2" data-testid="repair-finding" :value="terms.finding" maxlength="320" placeholder="Один подтверждённый факт" @input="update({finding: valueOf($event)})"></textarea>
      </label>
      <button v-if="!terms.finding && suggestions.savedFinding" type="button" class="link" @click="update({finding: suggestions.savedFinding})">Подставить результат диагностики из заказа</button>
    </div>
    <div class="space-y-1">
      <label class="field"><span>Что делать дальше</span>
        <textarea class="control" rows="2" data-testid="repair-recommendation" :value="terms.recommendation" maxlength="320" placeholder="Рекомендуемая работа или другое решение" @input="update({recommendation: valueOf($event)})"></textarea>
      </label>
      <button v-if="!terms.recommendation && suggestions.savedRecommendation && suggestions.savedRecommendation.length <= 320" type="button" class="link" @click="update({recommendation: suggestions.savedRecommendation})">Подставить рекомендацию из заказа</button>
    </div>
    <div class="grid min-w-0 gap-3 sm:grid-cols-2">
      <label class="field"><span>Стоимость ремонта</span>
        <input class="control" data-testid="repair-cost" :value="terms.cost || ''" maxlength="120" placeholder="Например, 240 BYN" @input="update({cost: valueOf($event) || null})" />
      </label>
      <label class="field"><span>Срок ремонта</span>
        <input class="control" data-testid="repair-term" :value="terms.term || ''" maxlength="120" placeholder="Например, 3 рабочих дня" @input="update({term: valueOf($event) || null})" />
      </label>
    </div>
    <p v-if="chargeRelevant" class="hint">Если цена или срок ремонта пока неизвестны, оставьте поле пустым.</p>
    <details class="min-w-0" :open="Boolean(terms.restriction)">
      <summary class="cursor-pointer text-xs font-semibold">Ограничение эксплуатации</summary>
      <label class="field mt-2"><span>До ремонта или следующей проверки</span>
        <input class="control" data-testid="repair-restriction" :value="terms.restriction || ''" maxlength="180" @input="update({restriction: valueOf($event) || null})" />
      </label>
    </details>
  </section>
</template>

<style scoped>
.repair-defect-form { @apply mt-4 grid min-w-0 gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900 sm:p-4; }
@media (max-width: 480px) {
  .repair-defect-form { @apply -mx-2; }
}
.field { @apply flex min-w-0 flex-col gap-1 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.control { @apply box-border min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm font-normal text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100; }
textarea.control { @apply resize-y; }
.link { @apply py-1 text-left text-xs font-semibold text-brand-700 underline dark:text-brand-300; }
.hint { @apply text-xs leading-5 text-slate-500 dark:text-slate-400; }
</style>
