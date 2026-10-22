<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ManagerOrderListItemResponse, ManagerOrderWaitingCommand } from '../../client';
import { toLocalDateTimeInput, fromLocalDateTimeInput } from '../../utils/datetime';
import { WAITING_REASONS } from '../../services/order-waiting';
import { useDialogA11y } from '../../composables/useDialogA11y';
const props = defineProps<{ order: ManagerOrderListItemResponse | null; busy: boolean; error: string; stale: boolean }>();
const emit = defineEmits<{ submit: [form: Omit<ManagerOrderWaitingCommand, 'action' | 'expected_revision'>]; close: []; refresh: [] }>();
const reason = ref<NonNullable<ManagerOrderWaitingCommand['reason_code']>>('next_stage');
const note = ref(''), contact = ref('');
const dialogRef = ref<HTMLElement | null>(null), reasonRef = ref<HTMLElement | null>(null);
watch(() => props.order?.id, () => {
  const order = props.order;
  if (!order) return;
  reason.value = (order.on_hold_reason_code as typeof reason.value) || (order.on_hold_reason ? 'other' : 'next_stage');
  note.value = order.on_hold_reason || '';
  contact.value = toLocalDateTimeInput(order.next_followup_date);
}, { immediate: true });
useDialogA11y({ open: computed(() => Boolean(props.order)), dialogRef, initialFocusRef: reasonRef, close: () => { if (!props.busy) emit('close'); } });
const submit = () => emit('submit', { reason_code: reason.value, note: note.value.trim() || null,
  next_followup_date: fromLocalDateTimeInput(contact.value) });
</script>
<template>
  <Teleport to="body"><div v-if="order" class="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-3" @click.self="!busy && emit('close')">
    <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="order-waiting-title" tabindex="-1" class="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-auto rounded-2xl bg-white p-5 text-slate-900 shadow-xl dark:bg-slate-900 dark:text-slate-100">
      <h2 id="order-waiting-title" class="text-lg font-semibold">В ожидание · заказ №{{ order.id }}</h2>
      <p class="mt-2 text-sm text-slate-500">Заказ останется на текущем этапе. Срок ожидания не обязателен.</p>
      <form class="mt-4 space-y-4" @submit.prevent="submit">
        <label class="block text-sm">Причина ожидания<select ref="reasonRef" v-model="reason" aria-label="Причина ожидания" class="mt-1 w-full rounded-lg border bg-white p-2 dark:bg-slate-800" :disabled="busy"><option v-for="option in WAITING_REASONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <label class="block text-sm">Пояснение<textarea v-model="note" aria-label="Пояснение ожидания" rows="3" maxlength="2000" :required="reason === 'other'" :disabled="busy" class="mt-1 w-full rounded-lg border bg-white p-2 dark:bg-slate-800" /></label>
        <label class="block text-sm">Контрольный контакт · необязательно<input v-model="contact" aria-label="Контрольный контакт" type="datetime-local" :disabled="busy" class="mt-1 block w-full min-w-0 rounded-lg border bg-white p-2 dark:bg-slate-800" /></label>
        <button v-if="contact" type="button" class="text-sm text-brand-700 underline" :disabled="busy" @click="contact = ''">Без даты контакта</button>
        <p class="text-xs text-slate-500">Контакт напомнит о заказе и сам не вернёт его в работу. Назначенные выезды и оплаты сохранятся.</p>
        <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
        <div class="flex flex-wrap gap-2"><button type="submit" :disabled="busy || stale" class="rounded-lg bg-brand-600 px-4 py-2 text-white disabled:opacity-50">{{ busy ? 'Сохраняем…' : 'В ожидание' }}</button><button v-if="stale" type="button" class="rounded-lg border px-3 py-2" :disabled="busy" @click="emit('refresh')">Обновить сведения</button><button type="button" :disabled="busy" class="rounded-lg px-3 py-2" @click="emit('close')">Отмена</button></div>
      </form>
    </section>
  </div></Teleport>
</template>
