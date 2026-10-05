<script setup lang="ts">
import { ref } from 'vue';
import type { ManagerOrderDocumentItem } from '../../../client';
import { useExternalContractRegistration } from '../composables/use-external-contract-registration';
import { EXTERNAL_CONTRACT_FILE_ACCEPT } from '../model/document-constants';

const props = defineProps<{ orderId: number; canCreate: boolean; accessSummary: string }>();
const emit = defineEmits<{
  registered: [document: ManagerOrderDocumentItem];
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();
const number = ref('');
const date = ref('');
const file = ref<File | null>(null);
const isSaving = ref(false);
const { handleExternalContractFile, registerExternalContract } = useExternalContractRegistration({
  orderId: () => props.orderId,
  canCreate: () => props.canCreate,
  accessSummary: () => props.accessSummary,
  number, date, file, isSaving,
  onRegistered: (document) => emit('registered', document),
  notify: (message, type = 'success') => emit('toast', { message, type }),
});
</script>

<template>
  <form class="mt-4 space-y-3" data-testid="external-contract-form" @submit.prevent="registerExternalContract">
    <p class="text-sm text-slate-600 dark:text-slate-300">Договор заказчика: укажите номер и дату для актов. Файл можно добавить сейчас или позже.</p>
    <fieldset class="space-y-3" :disabled="isSaving || !canCreate">
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="external-field">Номер договора
          <input v-model="number" class="external-input" data-testid="external-contract-number" required placeholder="Например, 44-ЭА/2026" />
        </label>
        <label class="external-field">Дата договора
          <input v-model="date" class="external-input" data-testid="external-contract-date" type="date" required />
        </label>
      </div>
      <label class="external-field">Файл договора · необязательно
        <input class="text-sm font-normal" data-testid="external-contract-file" type="file" :accept="EXTERNAL_CONTRACT_FILE_ACCEPT" @change="handleExternalContractFile" />
        <span class="font-normal text-slate-500">PDF, DOC, DOCX или фотография JPG/PNG.</span>
      </label>
      <button class="h-10 rounded-xl bg-brand-600 px-5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50" data-testid="save-external-contract" type="submit" :disabled="isSaving || !canCreate">
        {{ isSaving ? 'Сохраняем…' : 'Сохранить договор заказчика' }}
      </button>
    </fieldset>
  </form>
</template>

<style scoped>
.external-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.external-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
</style>
