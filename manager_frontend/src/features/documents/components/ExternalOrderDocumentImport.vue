<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { formatDocumentDate } from '../composables/use-native-document-basis';
import {
  EXTERNAL_DOCUMENT_MAX_BYTES, EXTERNAL_DOCUMENT_TYPES, PRIVATE_DOCUMENT_FILE_ACCEPT, externalOrderDocumentsApi,
  type ExternalDocumentEquipment, type ExternalDocumentSite, type ExternalDocumentStatus, type ExternalDocumentType,
  type ExternalDocumentUpload, type OrderDocumentWithEvidence,
} from '../integrations/external-order-documents-api';

const props = defineProps<{
  orderId: number;
  proposalId?: number | null;
  initialType?: ExternalDocumentType;
  sites: ExternalDocumentSite[];
  contracts: OrderDocumentWithEvidence[];
}>();
const emit = defineEmits<{ saved: [document: OrderDocumentWithEvidence]; cancel: []; busy: [saving: boolean] }>();
const documentType = ref<ExternalDocumentType>(props.initialType || 'contract');
const number = ref('');
const documentDate = ref(new Date().toLocaleDateString('sv-SE'));
const externalStatus = ref<ExternalDocumentStatus>('received');
const siteId = ref<number | null>(null);
const equipment = ref<ExternalDocumentEquipment[]>([]);
const equipmentIds = ref<number[]>([]);
const baseDocumentId = ref<number | null>(null);
const file = ref<File | null>(null);
const saving = ref(false);
const equipmentLoading = ref(false);
const equipmentError = ref('');
const error = ref('');
const isContract = computed(() => documentType.value === 'contract');
const needsFile = computed(() => !isContract.value || externalStatus.value === 'signed');
const siteRequired = computed(() => ['technical_inspection_act', 'defect_act'].includes(documentType.value));
let current = true;
let pending: { signature: string; file: File | null; key: string } | undefined;
onScopeDispose(() => { current = false; });

watch(documentType, () => {
  if (isContract.value) {
    siteId.value = null;
    baseDocumentId.value = null;
  }
});

watch(siteId, async (id, _old, onCleanup) => {
  equipmentIds.value = [];
  equipment.value = [];
  equipmentError.value = '';
  equipmentLoading.value = Boolean(id);
  if (!id) return;
  let active = true;
  onCleanup(() => { active = false; });
  try {
    const response = await externalOrderDocumentsApi.equipment(props.orderId, id);
    if (active) equipment.value = response.items;
  } catch (failure) {
    if (active) equipmentError.value = getApiErrorMessage(failure);
  } finally {
    if (active) equipmentLoading.value = false;
  }
});

const equipmentLabel = (item: ExternalDocumentEquipment) => {
  const unit = item.equipment;
  const name = unit.display_name || [unit.brand, unit.model].filter(Boolean).join(' ') || `Оборудование #${item.equipment_id}`;
  return unit.serial ? `${name} · ${unit.serial}` : name;
};
const pickFile = (event: Event) => { file.value = (event.target as HTMLInputElement).files?.[0] || null; };
const save = async () => {
  if (saving.value) return;
  error.value = '';
  if (!number.value.trim() || !documentDate.value) { error.value = 'Укажите номер и дату документа.'; return; }
  if (siteRequired.value && !siteId.value) { error.value = 'Выберите объект для технического акта.'; return; }
  if (needsFile.value && !file.value) { error.value = 'Выберите исходный файл.'; return; }
  if (file.value && (!file.value.size || file.value.size > EXTERNAL_DOCUMENT_MAX_BYTES)) {
    error.value = 'Размер файла должен быть от 1 байта до 10 МБ.';
    return;
  }
  const value: ExternalDocumentUpload = {
    document_type: documentType.value,
    number: number.value.trim(),
    document_date: documentDate.value,
    external_status: externalStatus.value,
    site_id: siteId.value || undefined,
    equipment_ids: [...equipmentIds.value],
    base_document_id: baseDocumentId.value || undefined,
    proposal_id: isContract.value ? undefined : props.proposalId || undefined,
    file: file.value,
  };
  const signature = JSON.stringify({ ...value, file: undefined });
  if (pending?.signature !== signature || pending.file !== file.value) {
    pending = { signature, file: file.value, key: crypto.randomUUID() };
  }
  saving.value = true;
  emit('busy', true);
  try {
    const saved = await externalOrderDocumentsApi.upload(props.orderId, value, pending.key);
    if (current) emit('saved', saved);
  } catch (failure) {
    if (current) error.value = getApiErrorMessage(failure);
  } finally {
    if (current) {
      saving.value = false;
      emit('busy', false);
    }
  }
};
</script>

<template>
  <form class="rounded-xl border border-slate-200 p-4 dark:border-slate-700" data-testid="external-document-import-form" @submit.prevent="save">
    <h5 class="mb-3 font-bold text-slate-900 dark:text-white">Импорт готового документа</h5>
    <fieldset class="grid gap-3 sm:grid-cols-2" :disabled="saving">
      <label class="evidence-field">Тип документа
        <select v-model="documentType" class="evidence-input" data-testid="external-document-type">
          <option v-for="item in EXTERNAL_DOCUMENT_TYPES" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <label class="evidence-field">Статус
        <select v-model="externalStatus" class="evidence-input" data-testid="external-document-status">
          <option value="received">Получен</option>
          <option value="signed">Подписан вне CRM</option>
        </select>
      </label>
      <label class="evidence-field">Номер
        <input v-model="number" class="evidence-input" maxlength="160" required data-testid="external-document-number" />
      </label>
      <label class="evidence-field">Дата
        <input v-model="documentDate" class="evidence-input" type="date" required data-testid="external-document-date" />
      </label>
      <label v-if="!isContract" class="evidence-field">Объект
        <select v-model="siteId" class="evidence-input" :required="siteRequired" data-testid="external-document-site">
          <option :value="null">{{ siteRequired ? 'Выберите объект' : 'Весь заказ' }}</option>
          <option v-for="site in sites" :key="site.id" :value="site.id">{{ site.title }} · {{ site.address }}</option>
        </select>
        <span v-if="siteRequired && sites.length === 0" class="font-normal text-slate-500">Добавьте объект в заказе, чтобы выбрать его здесь.</span>
      </label>
      <label v-if="!isContract" class="evidence-field">Договор-основание
        <select v-model="baseDocumentId" class="evidence-input" data-testid="external-document-basis">
          <option :value="null">Не выбран</option>
          <option v-for="contract in contracts" :key="contract.id" :value="contract.id">№ {{ contract.number }} от {{ formatDocumentDate(contract.date) }}</option>
        </select>
      </label>
      <div v-if="siteId" class="evidence-field sm:col-span-2" data-testid="external-document-equipment">
        <span>Оборудование объекта</span>
        <span v-if="equipmentLoading" role="status" class="font-normal">Загружаем оборудование…</span>
        <span v-else-if="equipmentError" role="alert" class="font-normal text-rose-700 dark:text-rose-300">{{ equipmentError }}</span>
        <span v-else-if="!equipment.length" class="font-normal">Оборудование ещё не добавлено.</span>
        <div v-else class="flex flex-wrap gap-2">
          <label v-for="unit in equipment" :key="unit.equipment_id" class="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-2 text-sm font-normal dark:border-slate-700">
            <input v-model="equipmentIds" type="checkbox" :value="unit.equipment_id" :data-testid="`external-equipment-${unit.equipment_id}`" />
            {{ equipmentLabel(unit) }}
          </label>
        </div>
      </div>
      <label class="evidence-field sm:col-span-2">Оригинал{{ needsFile ? '' : ' · необязательно' }}
        <input type="file" :required="needsFile" :accept="PRIVATE_DOCUMENT_FILE_ACCEPT" class="text-sm font-normal" data-testid="external-document-file" @change="pickFile" />
        <span class="font-normal text-slate-500">DOC, DOCX или PDF до 10 МБ.</span>
      </label>
    </fieldset>
    <p v-if="error" role="alert" class="mt-3 text-sm text-rose-700 dark:text-rose-300">{{ error }}</p>
    <div class="mt-4 flex flex-wrap gap-2">
      <button type="submit" class="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="saving || equipmentLoading || (siteRequired && !sites.length)" data-testid="save-external-document">{{ saving ? 'Сохраняем…' : 'Сохранить документ' }}</button>
      <button type="button" class="btn-mini px-4 py-2" :disabled="saving" @click="emit('cancel')">Отмена</button>
    </div>
  </form>
</template>

<style scoped>
.evidence-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.evidence-input { @apply min-h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-slate-700 dark:bg-slate-900 dark:text-white; }
</style>
