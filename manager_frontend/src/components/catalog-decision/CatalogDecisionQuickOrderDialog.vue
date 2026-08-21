<script setup lang="ts">
import { ref, watch } from 'vue';
import { ManagerCatalogDecisionService } from '../../client';
import type { CatalogDecisionSelectionItem } from '../../services/catalog-decision-selection';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ open: boolean; items: CatalogDecisionSelectionItem[] }>();
const emit = defineEmits<{ close: []; created: [orderId: number] }>();
const prospectType = ref<'individual' | 'company'>('individual');
const saving = ref(false);
const error = ref('');
const idempotencyKey = ref('');

const newIdempotencyKey = () => (
  globalThis.crypto?.randomUUID?.() || `quick-${Date.now()}-${Math.random().toString(16).slice(2)}`
);

watch(() => props.open, (open) => {
  if (!open) return;
  prospectType.value = 'individual';
  idempotencyKey.value = newIdempotencyKey();
  error.value = '';
}, { immediate: true });

const submit = async () => {
  if (saving.value || !props.items.length) return;
  saving.value = true;
  error.value = '';
  try {
    const order = await ManagerCatalogDecisionService.createManagerCatalogDecisionOrder({
      product_ids: props.items.map(item => item.id),
      idempotency_key: idempotencyKey.value,
      prospect_type: prospectType.value,
    });
    emit('created', order.id);
  } catch (err) {
    error.value = getApiErrorMessage(err) || 'Не удалось создать заказ';
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4" @click.self="emit('close')">
      <section class="w-full rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-lg sm:rounded-2xl">
        <div class="flex items-start justify-between gap-4">
          <div><h2 class="text-lg font-bold text-gray-900">Новый быстрый заказ</h2><p class="mt-1 text-sm text-gray-500">Контакты и реквизиты можно заполнить позже.</p></div>
          <button type="button" class="material-icons-round text-gray-400" aria-label="Закрыть" @click="emit('close')">close</button>
        </div>
        <p class="mt-5 text-sm font-medium text-gray-800">Кому готовим предложение?</p>
        <div class="mt-2 grid grid-cols-2 gap-2">
          <button type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="prospectType === 'individual' ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-gray-200 text-gray-700'" @click="prospectType = 'individual'">Физлицу</button>
          <button type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="prospectType === 'company' ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-gray-200 text-gray-700'" @click="prospectType = 'company'">Юрлицу</button>
        </div>
        <p class="mt-4 rounded-xl bg-gray-50 p-3 text-sm text-gray-600">Все {{ items.length }} выбранных моделей попадут в одно основное предложение — по 1 шт. Заказ сразу откроется в статусе «Переговоры».</p>
        <p v-if="error" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
        <div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded-xl px-4 py-2.5 text-sm font-semibold text-gray-600" @click="emit('close')">Отмена</button><button type="button" class="rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" :disabled="saving || !items.length" @click="submit">{{ saving ? 'Создаём…' : 'Создать заказ' }}</button></div>
      </section>
    </div>
  </Teleport>
</template>
