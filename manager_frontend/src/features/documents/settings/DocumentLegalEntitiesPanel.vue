<script setup lang="ts">
import { ref, watch } from 'vue';
import type { DocumentLegalEntityItem, DocumentLegalEntityUpdatePayload } from '../../../client';

const props = defineProps<{
  items: DocumentLegalEntityItem[];
  selectedId: number | null;
  loading: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  select: [id: number];
  create: [name: string];
  update: [id: number, changes: DocumentLegalEntityUpdatePayload];
}>();

const newName = ref('');
const legalName = ref('');
const unp = ref('');
const isVatPayer = ref(false);
const legalAddress = ref('');
const bankName = ref('');
const iban = ref('');
const bic = ref('');
const directorName = ref('');
const actsOnBasis = ref('');

const syncForm = () => {
  const entity = props.items.find((item) => item.id === props.selectedId);
  legalName.value = entity?.legal_name || '';
  unp.value = entity?.unp || '';
  isVatPayer.value = Boolean(entity?.is_vat_payer);
  legalAddress.value = entity?.requisites.legal_address || '';
  bankName.value = entity?.requisites.bank_name || '';
  iban.value = entity?.requisites.iban || '';
  bic.value = entity?.requisites.bic || '';
  directorName.value = entity?.requisites.director_name || '';
  actsOnBasis.value = entity?.requisites.acts_on_basis || '';
};

watch(() => [props.selectedId, props.items], syncForm, { immediate: true, deep: true });

const create = () => {
  const name = newName.value.trim();
  if (!name) return;
  emit('create', name);
  newName.value = '';
};

const save = () => {
  if (!props.selectedId) return;
  emit('update', props.selectedId, {
    legal_name: legalName.value.trim() || null,
    unp: unp.value.trim() || null,
    is_vat_payer: isVatPayer.value,
    requisites: {
      legal_address: legalAddress.value.trim() || null,
      bank_name: bankName.value.trim() || null,
      iban: iban.value.trim() || null,
      bic: bic.value.trim() || null,
      director_name: directorName.value.trim() || null,
      acts_on_basis: actsOnBasis.value.trim() || null,
    },
  });
};
</script>

<template>
  <section class="settings-card">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 class="settings-title">Юридические лица</h2>
        <p class="settings-help">Реквизиты продавца фиксируются в снимке при создании черновика.</p>
      </div>
      <span v-if="loading" class="material-icons-round animate-spin text-teal-600">progress_activity</span>
    </div>

    <div class="mt-5 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
      <div class="space-y-2">
        <button
          v-for="entity in items"
          :key="entity.id"
          type="button"
          class="w-full rounded-xl border p-3 text-left transition"
          :class="entity.id === selectedId ? 'border-teal-500 bg-teal-50 dark:bg-teal-950/30' : 'border-slate-200 hover:border-slate-300 dark:border-slate-700'"
          @click="emit('select', entity.id)"
        >
          <span class="flex items-center justify-between gap-3">
            <span class="font-semibold text-slate-900 dark:text-white">{{ entity.display_name }}</span>
            <span v-if="entity.is_default" class="rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-bold text-teal-800">По умолчанию</span>
          </span>
          <span class="mt-1 block text-xs text-slate-500">{{ entity.unp ? `УНП ${entity.unp}` : 'УНП не указан' }}</span>
        </button>

        <form class="flex gap-2 pt-2" @submit.prevent="create">
          <input v-model="newName" class="settings-input min-w-0 flex-1" placeholder="Например, ООО МВН" />
          <button class="settings-button-secondary" type="submit" :disabled="saving || !newName.trim()">+Юрлицо</button>
        </form>
      </div>

      <form v-if="selectedId" class="grid gap-4 sm:grid-cols-2" @submit.prevent="save">
        <label class="settings-field sm:col-span-2">
          <span>Полное наименование</span>
          <input v-model="legalName" class="settings-input" />
        </label>
        <label class="settings-field">
          <span>УНП</span>
          <input v-model="unp" class="settings-input" />
        </label>
        <button
          type="button"
          class="mt-6 flex h-10 items-center justify-between rounded-xl border px-3 text-sm font-semibold"
          :class="isVatPayer ? 'border-teal-500 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'"
          @click="isVatPayer = !isVatPayer"
        >
          <span>Плательщик НДС</span>
          <span class="material-icons-round text-[20px]">{{ isVatPayer ? 'toggle_on' : 'toggle_off' }}</span>
        </button>
        <label class="settings-field sm:col-span-2"><span>Юридический адрес</span><input v-model="legalAddress" class="settings-input" /></label>
        <label class="settings-field sm:col-span-2"><span>Банк</span><input v-model="bankName" class="settings-input" /></label>
        <label class="settings-field"><span>IBAN</span><input v-model="iban" class="settings-input" /></label>
        <label class="settings-field"><span>BIC</span><input v-model="bic" class="settings-input" /></label>
        <label class="settings-field"><span>ФИО подписанта</span><input v-model="directorName" class="settings-input" /></label>
        <label class="settings-field"><span>Действует на основании</span><input v-model="actsOnBasis" class="settings-input" placeholder="Устава" /></label>
        <div class="flex flex-wrap gap-2 sm:col-span-2">
          <button class="settings-button-primary" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить реквизиты' }}</button>
          <button
            v-if="!items.find((item) => item.id === selectedId)?.is_default"
            type="button"
            class="settings-button-secondary"
            :disabled="saving"
            @click="emit('update', selectedId, { is_default: true })"
          >Сделать основным</button>
        </div>
      </form>
      <p v-else class="self-center text-sm text-slate-500">Создайте первое юрлицо, чтобы настроить документы.</p>
    </div>
  </section>
</template>
