<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { getApiErrorMessage } from '../../utils/api-errors';
import { orderSourceReviewApi, sourceEquipmentPrefillMessage, type SourceEquipmentPreview, type SourceCommandHook, type SourceCommandEndHook } from '../../services/order-source-review';

const props = defineProps<{ orderId: number; proposalId?: number | null; compact?: boolean; beforeAction?: SourceCommandHook; afterAction?: SourceCommandHook; endAction?: SourceCommandEndHook }>();
const emit = defineEmits<{ applied: [orderId: number]; toast: [result: { message: string; type: 'success' | 'error' }] }>();
const expanded = ref(false);
const loading = ref(false);
const applying = ref(false);
const error = ref('');
const preview = ref<SourceEquipmentPreview | null>(null);
const selectedIds = ref<number[]>([]);
const restoreIds = ref<number[]>([]);
let requestVersion = 0;
let commandIntent: { key: string; id: string } | null = null;
const sameScope = (orderId: number, proposalId: number | null | undefined, version: number) => props.orderId === orderId && props.proposalId === proposalId && requestVersion === version;
const selectableCount = computed(() => selectedIds.value.length + restoreIds.value.length);
const formatMoney = (value?: number | null) => value == null ? '—' : `${value.toLocaleString('ru-RU')} BYN`;
const load = async () => {
  const orderId = props.orderId; const proposalId = props.proposalId; const version = ++requestVersion;
  loading.value = true; error.value = '';
  try {
    const result = await orderSourceReviewApi.equipment(orderId, proposalId);
    if (!sameScope(orderId, proposalId, version)) return;
    preview.value = result;
    selectedIds.value = result.items.filter((item) => item.can_add && item.product_id).map((item) => item.product_id!);
    restoreIds.value = [];
  } catch (reason) { if (sameScope(orderId, proposalId, version)) error.value = getApiErrorMessage(reason); }
  finally { if (sameScope(orderId, proposalId, version)) loading.value = false; }
};
const toggle = async () => {
  expanded.value = !expanded.value;
  if (expanded.value) await load();
};
const apply = async () => {
  if (applying.value || !preview.value?.proposal_id || !selectableCount.value) return;
  const orderId = props.orderId; const proposalId = props.proposalId; const version = requestVersion;
  const intentKey = JSON.stringify([orderId, preview.value.proposal_id, preview.value.preview_fingerprint,
    [...selectedIds.value].sort((a, b) => a - b), [...restoreIds.value].sort((a, b) => a - b)]);
  if (commandIntent?.key !== intentKey) commandIntent = { key: intentKey, id: crypto.randomUUID() };
  const payload = {
    proposal_id: preview.value.proposal_id, command_id: commandIntent.id,
    preview_fingerprint: preview.value.preview_fingerprint,
    product_ids: [...selectedIds.value, ...restoreIds.value], restore_removed_product_ids: [...restoreIds.value],
  };
  applying.value = true; error.value = '';
  let started = false;
  let applied = false;
  try {
    if (await props.beforeAction?.() === false) return;
    started = true;
    if (!sameScope(orderId, proposalId, version)) return;
    const result = await orderSourceReviewApi.addEquipment(orderId, payload);
    applied = true;
    if (!sameScope(orderId, proposalId, version)) return;
    if (await props.afterAction?.() === false || !sameScope(orderId, proposalId, version)) return;
    emit('toast', { message: sourceEquipmentPrefillMessage(result) || 'Подбор из заявки применён', type: 'success' });
    emit('applied', orderId);
    await load();
  } catch (reason) {
    if (sameScope(orderId, proposalId, version)) error.value = `${applied ? 'Товары добавлены, но карточку не удалось обновить. Повторно откройте заказ. ' : ''}${getApiErrorMessage(reason)}`;
  } finally { if (started) props.endAction?.(); applying.value = false; }
};
watch(() => [props.orderId, props.proposalId] as const, () => {
  commandIntent = null;
  requestVersion++; preview.value = null; selectedIds.value = []; restoreIds.value = []; error.value = ''; loading.value = false;
  if (expanded.value) void load();
});
</script>

<template>
  <section :class="compact ? 'contents' : 'mb-3 text-sm'" aria-label="Товары из заявки">
    <button type="button" class="btn-mini-outline" :class="compact ? 'h-8 text-xs' : ''" :disabled="applying" :aria-expanded="expanded" @click="toggle">{{ expanded ? 'Скрыть подбор из заявки' : 'Добавить из заявки' }}</button>
    <div v-if="expanded" class="mt-3 space-y-3" :class="compact ? 'basis-full text-sm' : ''">
      <p v-if="loading" role="status" class="text-slate-500">Проверяем модели, цену и наличие…</p>
      <p v-if="error" role="alert" class="text-red-700">{{ error }} <button type="button" class="underline" :disabled="applying || loading" @click="load">Обновить подбор</button></p>
      <template v-if="preview">
        <p class="text-xs text-slate-500">Только точные совпадения. Уже добавленные строки сохраняют цену и количество. Остаток не резервируется.</p>
        <p v-for="warning in preview.warnings" :key="warning" class="text-xs text-amber-800">{{ warning }}</p>
        <div v-if="preview.items.length" class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead><tr class="border-b border-slate-200"><th class="py-2 pr-2">Модель из заявки</th><th class="py-2 pr-2">Шт.</th><th class="py-2 pr-2">Цена / наличие</th><th class="py-2">Результат</th></tr></thead>
            <tbody><tr v-for="(item, index) in preview.items" :key="`${item.product_id || 'missing'}-${index}`" class="border-b border-slate-100 align-top">
              <td class="max-w-64 py-2 pr-2 break-words">{{ [item.brand, item.model].filter(Boolean).join(' ') || 'Модель не указана' }}</td>
              <td class="py-2 pr-2">{{ item.quantity ?? '—' }}</td>
              <td class="whitespace-nowrap py-2 pr-2">{{ formatMoney(item.price) }}<span class="block text-slate-500">{{ item.available_quantity == null ? '—' : `${item.available_quantity} шт. доступно` }}</span></td>
              <td class="py-2"><label v-if="item.can_add && item.product_id" class="flex gap-2"><input v-model="selectedIds" type="checkbox" :value="item.product_id" :disabled="applying" />Добавить</label><label v-else-if="item.can_restore && item.product_id" class="flex gap-2"><input v-model="restoreIds" type="checkbox" :value="item.product_id" :disabled="applying" />{{ item.reason === 'previously_added_elsewhere' ? 'Добавить повторно' : 'Восстановить удалённое' }}</label><p class="mt-1 text-slate-600">{{ item.message }}</p></td>
            </tr></tbody>
          </table>
        </div>
        <button type="button" class="btn-mini" :disabled="applying || loading || !selectableCount" @click="apply">{{ applying ? 'Добавляем…' : `Добавить выбранное (${selectableCount})` }}</button>
      </template>
    </div>
  </section>
</template>
