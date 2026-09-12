<script setup lang="ts">
import { ref, watch } from 'vue';
import { Link2, X } from 'lucide-vue-next';

const props = defineProps<{
  receiptId: number;
  open: boolean;
  busy: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  open: [];
  cancel: [];
  attach: [orderId: number];
}>();

const orderId = ref<string | number>('');
const validationError = ref('');

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    orderId.value = '';
    validationError.value = '';
  },
);

const submit = () => {
  const normalizedOrderId = Number(String(orderId.value ?? '').trim());
  if (!Number.isInteger(normalizedOrderId) || normalizedOrderId <= 0) {
    validationError.value = 'Укажите корректный номер заказа.';
    return;
  }
  validationError.value = '';
  emit('attach', normalizedOrderId);
};
</script>

<template>
  <div class="mt-2 min-w-[190px]">
    <div
      v-if="open"
      class="rounded-lg border border-brand-200 bg-brand-50 p-2 dark:border-brand-500/30 dark:bg-brand-500/10"
      :data-testid="`manual-attach-form-${receiptId}`"
    >
      <label class="block text-xs font-semibold text-brand-900 dark:text-brand-100">
        Номер заказа
        <input
          v-model="orderId"
          class="mt-1 w-full rounded-md border border-brand-300 bg-white px-2 py-1.5 text-sm text-slate-950 dark:border-brand-500/40 dark:bg-slate-950 dark:text-white"
          type="number"
          min="1"
          step="1"
          inputmode="numeric"
          placeholder="Например 279"
          :disabled="busy"
          :data-testid="`manual-attach-order-${receiptId}`"
          @keyup.enter="submit"
        />
      </label>
      <div class="mt-2 flex gap-1.5">
        <button
          type="button"
          class="inline-flex min-h-8 flex-1 items-center justify-center gap-1 rounded-md bg-brand-600 px-2 text-xs font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          :disabled="busy"
          :data-testid="`manual-attach-submit-${receiptId}`"
          @click="submit"
        >
          <Link2 class="h-3.5 w-3.5" />
          {{ busy ? 'Привязываем...' : 'Привязать' }}
        </button>
        <button
          type="button"
          class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-brand-300 text-brand-800 hover:bg-white disabled:opacity-50 dark:border-brand-500/40 dark:text-brand-200 dark:hover:bg-slate-950"
          :disabled="busy"
          aria-label="Отменить привязку"
          @click="emit('cancel')"
        >
          <X class="h-3.5 w-3.5" />
        </button>
      </div>
      <p v-if="validationError || error" class="mt-2 text-xs font-medium text-red-700 dark:text-red-300">
        {{ validationError || error }}
      </p>
    </div>
    <button
      v-else
      type="button"
      class="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-700 hover:text-brand-900 dark:text-brand-300 dark:hover:text-brand-100"
      :data-testid="`manual-attach-start-${receiptId}`"
      @click="emit('open')"
    >
      <Link2 class="h-3.5 w-3.5" />
      Привязать заказ
    </button>
  </div>
</template>
