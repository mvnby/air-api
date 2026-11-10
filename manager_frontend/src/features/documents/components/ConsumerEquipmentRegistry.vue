<script setup lang="ts">
import { ref, watch } from 'vue';
import { ManagerOrderEquipmentService, type OrderEquipmentIdentity, type OrderEquipmentState, type OrderEquipmentSavePayload } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import type { ConsumerDocumentTerms } from '../model/consumer-document-terms';

const props = defineProps<{ orderId: number; terms: ConsumerDocumentTerms; sourceDocumentId?: number | null }>();
const emit = defineEmits<{ updateTerms: [terms: ConsumerDocumentTerms] }>();
const state = ref<OrderEquipmentState | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const message = ref('');
let pending: OrderEquipmentSavePayload | null = null;
let generation = 0;

const load = async () => {
  const request = ++generation;
  loading.value = true;
  try {
    const result = await ManagerOrderEquipmentService.getManagerOrderEquipmentIdentities(props.orderId);
    if (request === generation) state.value = result;
  } catch (cause) {
    if (request === generation) error.value = getApiErrorMessage(cause);
  } finally {
    if (request === generation) loading.value = false;
  }
};
watch(() => props.orderId, () => { state.value = null; pending = null; error.value = ''; message.value = ''; void load(); }, { immediate: true });
const selectIdentity = (identity?: OrderEquipmentIdentity) => {
  pending = null;
  message.value = '';
  emit('updateTerms', { ...props.terms, equipment_id: identity?.equipment_id ?? null,
    ...(identity ? { equipment_brand: identity.brand, equipment_model: identity.model, equipment_serial: identity.serial } : {}),
  });
};
const choose = (event: Event) => selectIdentity(state.value?.items.find(item => item.equipment_id === Number((event.target as HTMLSelectElement).value)));
const refreshIdentity = async () => {
  await load();
  const identity = state.value?.items.find(item => item.equipment_id === props.terms.equipment_id);
  if (identity) selectIdentity(identity);
};
const reread = () => { pending = null; error.value = ''; return load(); };
const save = async () => {
  if (!state.value || saving.value) return;
  const orderId = props.orderId;
  const current = state.value.items.find(item => item.equipment_id === props.terms.equipment_id);
  const fields = { equipment_id: props.terms.equipment_id,
    expected_equipment_version: current?.version,
    source_document_id: props.sourceDocumentId,
    brand: props.terms.equipment_brand, model: props.terms.equipment_model, serial: props.terms.equipment_serial,
  };
  // Retain the exact payload/key after a timeout. A changed form starts another explicit command.
  if (!pending || JSON.stringify({ ...pending, idempotency_key: undefined, expected_version: undefined }) !== JSON.stringify(fields)) {
    pending = { ...fields, expected_version: state.value.version, idempotency_key: crypto.randomUUID() };
  }
  saving.value = true;
  error.value = '';
  try {
    const result = await ManagerOrderEquipmentService.saveManagerOrderEquipmentIdentity(orderId, pending);
    if (props.orderId !== orderId) return;
    // Saving the registry does not refresh the document's captured identity.
    emit('updateTerms', { ...props.terms, equipment_id: result.result.equipment_id });
    pending = null;
    message.value = 'Сохранено в реестре и связано с заказом';
    await load();
  } catch (cause) {
    if (props.orderId === orderId) error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div class="mt-3 space-y-2 rounded-lg border border-brand-200 p-3 dark:border-brand-900" data-testid="consumer-equipment-registry">
    <label class="flex flex-col gap-1 text-sm font-semibold">Оборудование заказа
      <select class="h-10 rounded-lg border border-slate-300 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900" :value="terms.equipment_id ?? ''" :disabled="loading || saving" data-testid="consumer-equipment-choice" @change="choose">
        <option value="">Сведения вручную / из документа</option>
        <option v-for="item in state?.items ?? []" :key="item.equipment_id" :value="item.equipment_id">#{{ item.equipment_id }} · {{ item.brand }} {{ item.model }} · {{ item.serial || 'серийный номер неизвестен' }}</option>
      </select>
    </label>
    <p class="text-xs text-slate-500">Сведения документа сохраняются отдельно от карточки. Другие единицы можно привязать в разделе «Оборудование» заказа.</p>
    <div class="flex flex-wrap gap-2">
      <button v-if="terms.equipment_id" type="button" class="btn-mini-outline" :disabled="loading || saving" data-testid="consumer-equipment-refresh" @click="refreshIdentity">Взять актуальные данные карточки</button>
      <button type="button" class="btn-mini-outline" :disabled="!state || saving || loading || !(terms.equipment_brand || terms.equipment_model || terms.equipment_serial)" data-testid="consumer-equipment-save" @click="save">{{ saving ? 'Сохраняем…' : terms.equipment_id ? 'Сохранить сведения в карточке' : 'Сохранить в реестр и заказ' }}</button>
      <button v-if="error" type="button" class="btn-mini-outline" :disabled="loading || saving" @click="reread">Перечитать оборудование</button>
    </div>
    <p v-if="message" class="text-xs text-emerald-700" role="status">{{ message }}</p>
    <p v-if="error" class="text-xs text-red-700" role="alert">{{ error }}</p>
  </div>
</template>
