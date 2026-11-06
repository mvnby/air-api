<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ManagerDocumentSystemService, type WaybillComponent, type WaybillComposition_Input, type WaybillSourceLine } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { centsToAmount, formatByn, moneyToCents } from '../model/installation-two-stages';

const props = defineProps<{
  orderId: number; proposalId: number | null; replacementId?: number | null; prior?: WaybillComposition_Input | null;
}>();
const emit = defineEmits<{ change: [choice: WaybillComposition_Input | null] }>();
type Group = { source: WaybillSourceLine; wholeCountry: string; split: boolean; parts: WaybillComponent[] };
const groups = ref<Group[]>([]);
const revision = ref('');
const error = ref('');
const loading = ref(false);
const recheck = ref(false);
const retry = ref(0);
const newPart = (): WaybillComponent => ({
  title: '', country: '', unit: 'шт.', quantity_per_parent: 1, unit_price: '',
});
const setSplit = (group: Group, split: boolean) => {
  group.split = split;
  if (split && !group.parts.length) group.parts.push(newPart(), newPart());
};
const perSet = (group: Group): number | null => {
  if (!group.split) return moneyToCents(group.source.unit_price);
  let total = 0;
  for (const part of group.parts) {
    const price = moneyToCents(part.unit_price);
    if (price === null || !Number.isInteger(part.quantity_per_parent) || part.quantity_per_parent <= 0
      || part.quantity_per_parent > 1_000_000) return null;
    total += price * part.quantity_per_parent;
  }
  return Number.isSafeInteger(total) ? total : null;
};
const groupError = (group: Group) => {
  if (!group.split) return '';
  if (!group.parts.length) return 'Добавьте хотя бы одну позицию комплекта.';
  if (group.parts.some(part => !part.title.trim() || !part.unit.trim()))
    return 'Заполните название и единицу для каждой позиции.';
  const amount = perSet(group);
  if (amount === null) return 'Количество должно быть целым. Цены вводите с точностью до копейки.';
  if (amount !== moneyToCents(group.source.unit_price)) return 'Сумма позиций должна совпасть с ценой одного комплекта.';
  return '';
};
watch([() => props.orderId, () => props.proposalId, () => props.replacementId, retry, () => props.prior?.source_revision], async (context, previous, cleanup) => {
  let current = true;
  cleanup(() => { current = false; });
  groups.value = []; revision.value = ''; error.value = ''; loading.value = true; recheck.value = false;
  try {
    const source = await ManagerDocumentSystemService.getManagerWaybillComposition(props.orderId, props.proposalId);
    if (!current) return;
    const resetting = previous.length > 0 && context[3] !== previous[3];
    const reusable = !resetting && props.prior?.source_revision === source.source_revision ? props.prior : null;
    recheck.value = !!(props.replacementId || props.prior) && !reusable;
    groups.value = source.lines.map(line => {
      const saved = reusable?.lines.find(item => item.order_product_line_id === line.order_product_line_id);
      const parts = saved ? saved.components : line.components;
      return { source: line, wholeCountry: saved?.whole_country ?? line.country, split: !!parts?.length, parts: (parts || []).map(part => ({ ...part })) };
    });
    revision.value = source.source_revision;
  } catch (err) { if (current) error.value = getApiErrorMessage(err); }
  finally { if (current) loading.value = false; }
}, { immediate: true, flush: 'sync' });
const selection = computed<WaybillComposition_Input | null>(() => {
  if (loading.value || !revision.value || recheck.value || !groups.value.length || groups.value.some(group => groupError(group))) return null;
  return { source_revision: revision.value, lines: groups.value.map(group => ({
    order_product_line_id: group.source.order_product_line_id,
    ...(!group.split && group.wholeCountry !== group.source.country ? {whole_country: group.wholeCountry.trim()} : {}),
    components: group.split ? group.parts.map(part => ({ ...part, unit_price: centsToAmount(moneyToCents(part.unit_price)!) })) : null,
  })) };
});
watch(selection, value => emit('change', value), { immediate: true, flush: 'sync' });
</script>

<template>
  <section class="my-4 min-w-0 space-y-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700" data-testid="native-waybill-composition">
    <header class="flex flex-wrap items-center justify-between gap-2">
      <h4 class="text-sm font-semibold">Состав накладной</h4>
      <button v-if="!loading" type="button" class="text-xs text-brand-700 underline dark:text-brand-300" @click="retry++">{{ error ? 'Повторить загрузку' : 'Сбросить к предложению' }}</button>
    </header>
    <p v-if="loading" class="text-xs">Загрузка товаров…</p>
    <p v-else-if="error" class="text-sm text-rose-700" role="alert">{{ error }}</p>
    <p v-else-if="!groups.length" class="text-sm">В выбранном предложении нет товаров.</p>
    <div v-if="recheck" class="space-y-1 text-sm">
      <p>Сверьте состав исправленной накладной с исходным документом.</p>
      <button type="button" class="text-brand-700 underline" @click="recheck = false">Состав проверен</button>
    </div>
    <details v-for="group in groups" :key="group.source.order_product_line_id" :open="groups.length === 1"
      class="min-w-0 rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800">
      <summary class="cursor-pointer break-words text-sm [overflow-wrap:anywhere]">
        <strong>{{ group.source.title }}</strong>
        <span v-if="groupError(group)" class="ml-1 text-xs text-amber-800 dark:text-amber-300">Проверьте позиции</span>
        <span class="mt-1 block text-xs text-slate-600 dark:text-slate-300">{{ group.source.quantity }} × {{ formatByn(moneyToCents(group.source.unit_price)) }} · {{ group.split ? 'По частям' : 'Целиком' }}</span>
      </summary>
      <div class="mt-3 flex flex-wrap gap-2" aria-label="Печатать товар">
        <button v-for="option in [{split:false,label:'Целиком'}, {split:true,label:'По частям'}]" :key="option.label" type="button"
          class="min-h-10 rounded-lg border px-3 text-xs font-semibold" :class="group.split === option.split ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300'"
          :aria-pressed="group.split === option.split" @click="setSplit(group, option.split)">{{ option.label }}</button>
      </div>
      <label v-if="!group.split" class="mt-3 grid min-w-0 gap-1 text-xs font-semibold">
        Страна происхождения
        <input v-model="group.wholeCountry" maxlength="160" placeholder="Если известна" class="min-h-10 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-2 text-sm font-normal dark:border-slate-600 dark:bg-slate-950" />
      </label>
      <div v-else class="mt-3 space-y-3">
        <div v-for="(part, index) in group.parts" :key="index" class="part-grid rounded-lg border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900">
          <label class="col-span-2">Название позиции<textarea v-model="part.title" rows="2" maxlength="500"></textarea></label>
          <label>Количество на комплект<input v-model.number="part.quantity_per_parent" type="number" min="1" max="1000000" /></label>
          <label>Цена за единицу, BYN<input v-model="part.unit_price" inputmode="decimal" maxlength="15" placeholder="0,00" /></label>
          <details class="col-span-2 min-w-0">
            <summary class="cursor-pointer text-xs text-slate-600 dark:text-slate-300">{{ part.country || 'Страна' }} · {{ part.unit || 'Единица' }}</summary>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <label>Страна<input v-model="part.country" maxlength="160" placeholder="Если известна" /></label>
              <label>Единица<input v-model="part.unit" maxlength="40" /></label>
            </div>
          </details>
          <button type="button" class="col-span-2 w-fit min-h-8 text-xs text-slate-600 underline dark:text-slate-300" @click="group.parts.splice(index, 1)">Убрать позицию</button>
        </div>
        <button v-if="group.parts.length < 100" type="button" class="min-h-10 rounded-lg border border-slate-300 px-3 text-sm" @click="group.parts.push(newPart())">Добавить позицию</button>
        <p class="text-xs">Состав на один комплект: <strong>{{ formatByn(perSet(group)) }}</strong> из {{ formatByn(moneyToCents(group.source.unit_price)) }}</p>
        <p v-if="groupError(group)" class="text-xs text-amber-800 dark:text-amber-300" role="status">{{ groupError(group) }}</p>
      </div>
    </details>
  </section>
</template>

<style scoped>
.part-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem; }
.part-grid label { @apply flex min-w-0 flex-col justify-between gap-1 break-words text-xs font-semibold; }
.part-grid input, .part-grid textarea { @apply min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-2 text-sm font-normal dark:border-slate-600 dark:bg-slate-950; }
.part-grid textarea { @apply resize-y py-2; }
@media (max-width: 350px) {
  .part-grid { grid-template-columns: minmax(0, 1fr); }
  .part-grid .col-span-2 { grid-column: auto; }
}
</style>
