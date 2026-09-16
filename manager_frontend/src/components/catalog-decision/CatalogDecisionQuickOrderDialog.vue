<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { ManagerCatalogDecisionService } from '../../client';
import type { CatalogDecisionSelectionItem } from '../../services/catalog-decision-selection';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ open: boolean; items: CatalogDecisionSelectionItem[] }>();
const emit = defineEmits<{ close: []; created: [orderId: number] }>();
const prospectType = ref<'individual' | 'company'>('individual');
const proposalMode = ref<'alternatives' | 'bundle'>('alternatives');
const dialogRef = ref<HTMLElement | null>(null);
const saving = ref(false);
const close = () => { if (!saving.value) emit('close'); };
useDialogA11y({ open: computed(() => props.open), dialogRef, close });
const error = ref('');
const idempotencyKey = ref('');

const newIdempotencyKey = () => (
  globalThis.crypto?.randomUUID?.() || `quick-${Date.now()}-${Math.random().toString(16).slice(2)}`
);

watch(() => props.open, (open) => {
  if (!open) return;
  prospectType.value = 'individual';
    proposalMode.value = props.items.length > 1 ? 'alternatives' : 'bundle';
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
      proposal_mode: proposalMode.value,
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
    <div v-if="open" class="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4" @click.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="quick-order-title" tabindex="-1" class="w-full rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-lg sm:rounded-2xl">
        <div class="flex items-start justify-between gap-4">
          <div><h2 id="quick-order-title" class="text-lg font-bold text-gray-900">Новый быстрый заказ</h2><p class="mt-1 text-sm text-gray-500">Контакты и реквизиты можно заполнить позже.</p></div>
          <button type="button" class="material-icons-round text-gray-400" aria-label="Закрыть" @click="close">close</button>
        </div>
        <p class="mt-5 text-sm font-medium text-gray-800">Кому готовим предложение?</p>
        <div class="mt-2 grid grid-cols-2 gap-2">
          <button type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="prospectType === 'individual' ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 text-gray-700'" :disabled="saving" @click="prospectType = 'individual'">Физлицу</button>
          <button type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="prospectType === 'company' ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 text-gray-700'" :disabled="saving" @click="prospectType = 'company'">Юрлицу</button>
        </div>
        <fieldset v-if="items.length > 1" class="mt-4">
          <legend class="text-sm font-medium text-gray-800">Как предложить модели клиенту?</legend>
          <div class="mt-2 grid grid-cols-2 gap-2">
            <button v-for="mode in (['alternatives', 'bundle'] as const)" :key="mode" type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="proposalMode === mode ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 text-gray-700'" :aria-pressed="proposalMode === mode" :disabled="saving" @click="proposalMode = mode">{{ mode === 'alternatives' ? 'Альтернативы' : 'Один комплект' }}</button>
          </div>
        </fieldset>
        <p class="mt-4 rounded-xl bg-gray-50 p-3 text-sm text-gray-600">{{ proposalMode === 'alternatives' ? `Каждая из ${items.length} моделей — отдельный вариант предложения. Клиент выберет подходящий.` : `Все модели войдут в одно предложение по 1 шт. Количества можно изменить в заказе.` }} Заказ будет создан в статусе «Переговоры».</p>
        <p v-if="error" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
        <div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded-xl px-4 py-2.5 text-sm font-semibold text-gray-600" @click="close">Отмена</button><button type="button" class="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" :disabled="saving || !items.length" @click="submit">{{ saving ? 'Создаём…' : 'Создать заказ' }}</button></div>
      </section>
    </div>
  </Teleport>
</template>
