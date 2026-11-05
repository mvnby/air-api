<script setup lang="ts">
import { computed, ref } from 'vue';
import { Archive, ExternalLink, Trash2 } from 'lucide-vue-next';
import { ManagerContractsService, type DocumentLegalEntityItem, type ManagerCustomerContractItemResponse } from '../../client';
import { DOCUMENT_ROLE_OPTIONS } from '../../features/documents/model/document-constants';
import { orderPageUrl } from '../../services/order-navigation';
import { getApiErrorMessage } from '../../utils/api-errors';
import { toLocalDateTimeInput } from '../../utils/datetime';

const props = defineProps<{
  contract: ManagerCustomerContractItemResponse;
  issuers: DocumentLegalEntityItem[];
  issuersLoading: boolean;
  issuersError: string;
  canManage: boolean;
  ordersUrl: string;
  editInitially?: boolean;
}>();
const emit = defineEmits<{
  saved: [];
  retryIssuers: [];
  archive: [contract: ManagerCustomerContractItemResponse];
  delete: [contract: ManagerCustomerContractItemResponse];
}>();
const native = computed(() => props.contract.source_kind === 'crm' || props.contract.source_document_id != null);
const editing = ref(Boolean(props.editInitially && props.canManage && !native.value && props.contract.status === 'active'));
const saving = ref(false);
const saveError = ref('');
const selectedIssuer = ref<number | null>(props.contract.legal_entity_id ?? null);
const selectedRole = ref(props.contract.document_role_type || '');
const sourceUrl = computed(() => props.contract.source_order_id
  ? orderPageUrl(props.contract.source_order_id, props.ordersUrl, null, 'documents') : '');
const issuer = computed(() => props.issuers.find(item => item.id === props.contract.legal_entity_id));
const activeIssuers = computed(() => props.issuers.filter(item => item.status === 'active'));
const role = computed(() => DOCUMENT_ROLE_OPTIONS.find(item => item.value === props.contract.document_role_type)?.label);
const dateLabel = (value: string) => value.slice(0, 10).split('-').reverse().join('.');
const status = computed(() => {
  if (props.contract.status !== 'active') return 'Архив';
  const today = toLocalDateTimeInput(new Date().toISOString()).slice(0, 10);
  if (props.contract.valid_until.slice(0, 10) < today) return 'Срок истёк';
  if (props.contract.valid_from.slice(0, 10) > today) return 'Ожидает начала';
  return 'Активен';
});
const edit = () => {
  selectedIssuer.value = props.contract.legal_entity_id ?? null;
  selectedRole.value = props.contract.document_role_type || '';
  saveError.value = '';
  editing.value = true;
};
const canSave = computed(() => props.canManage && !native.value && !saving.value &&
  activeIssuers.value.some(item => item.id === selectedIssuer.value) &&
  DOCUMENT_ROLE_OPTIONS.some(item => item.value === selectedRole.value) &&
  (props.contract.legal_entity_id !== selectedIssuer.value || props.contract.document_role_type !== selectedRole.value));
const save = async () => {
  if (!canSave.value || !selectedIssuer.value) return;
  saving.value = true;
  saveError.value = '';
  try {
    await ManagerContractsService.patchManagerCustomerContract(props.contract.customer_id, props.contract.id, {
      legal_entity_id: selectedIssuer.value, document_role_type: selectedRole.value,
    });
    editing.value = false;
    emit('saved');
  } catch (error) {
    saveError.value = getApiErrorMessage(error);
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <li class="contract-row" :data-testid="`contract-row-${contract.id}`">
    <div class="contract-summary">
      <div class="min-w-0">
        <div class="contract-title"><strong>№ {{ contract.number }}</strong><span :class="status === 'Активен' ? 'badge' : 'status-note'">{{ status }}</span></div>
        <p class="detail-line">{{ dateLabel(contract.valid_from) }} — {{ dateLabel(contract.valid_until) }}</p>
        <p class="parties">{{ issuer?.legal_name || issuer?.display_name || (contract.legal_entity_id ? `Юрлицо №${contract.legal_entity_id}` : 'Наше юрлицо не указано') }} · {{ role || 'Роли не указаны' }}</p>
      </div>
      <div class="contract-actions">
        <a v-if="native && sourceUrl" class="workspace-link source" :href="sourceUrl" target="_blank" rel="noopener noreferrer">CRM · заказ №{{ contract.source_order_id }} <ExternalLink :size="13" aria-hidden="true" /></a>
        <span v-else-if="native" class="source">Договор CRM</span>
        <a v-else-if="contract.edit_url" class="workspace-link source" :href="contract.edit_url" target="_blank" rel="noopener noreferrer">Google Drive <ExternalLink :size="13" aria-hidden="true" /></a>
        <span v-else class="source">Договор Google</span>
        <button v-if="canManage && !native && contract.status === 'active' && !editing" type="button" class="workspace-link source" @click="edit">Изменить стороны</button>
      </div>
      <div v-if="canManage && (contract.status === 'active' || contract.can_delete)" class="contract-management">
        <button v-if="canManage && contract.status === 'active'" type="button" :disabled="saving" class="icon-action" aria-label="Архивировать договор" title="Архивировать договор" @click="emit('archive', contract)"><Archive :size="16" /></button>
        <button v-if="canManage && contract.can_delete && !native" type="button" :disabled="saving" class="icon-action delete" aria-label="Удалить договор" title="Удалить договор" @click="emit('delete', contract)"><Trash2 :size="16" /></button>
      </div>
    </div>
    <form v-if="editing && canManage && !native" class="parties-form" @submit.prevent="save">
      <div class="form-grid">
        <label class="field-label">Наше юрлицо или ИП
          <select v-model="selectedIssuer" class="field-input" :disabled="issuersLoading || saving" required>
            <option :value="null" disabled>Выберите по договору</option>
            <option v-for="item in activeIssuers" :key="item.id" :value="item.id">{{ item.legal_name || item.display_name }}</option>
          </select>
        </label>
        <label class="field-label">Названия сторон
          <select v-model="selectedRole" class="field-input" required :disabled="saving">
            <option value="" disabled>Выберите по договору</option>
            <option v-for="item in DOCUMENT_ROLE_OPTIONS" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
      </div>
      <p v-if="issuersError" class="field-error mt-2" role="alert">{{ issuersError }} <button class="workspace-link" type="button" @click="emit('retryIssuers')">Повторить</button></p>
      <p v-else-if="!issuersLoading && !activeIssuers.length" class="detail-line">Для выбора нужно действующее юрлицо в настройках документов.</p>
      <p v-if="saveError" class="field-error mt-2" role="alert">{{ saveError }}</p>
      <div class="form-actions"><button type="button" class="btn-mini-outline" :disabled="saving" @click="editing = false">Отмена</button><button type="submit" class="btn-mini" :disabled="!canSave">{{ saving ? 'Сохраняем…' : 'Сохранить стороны' }}</button></div>
    </form>
  </li>
</template>

<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.contract-row { padding: 12px 0; border-top: 1px solid var(--mv-border); min-width: 0; }
.contract-summary { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 4px 10px; align-items: center; }
.contract-actions, .contract-title, .contract-management { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.contract-title { font-size: 14px; overflow-wrap: anywhere; }
.parties, .detail-line, .status-note { color: var(--mv-text-muted); font-size: 12px; overflow-wrap: anywhere; }
.parties, .detail-line { margin-top: 4px; }
.source { display: inline-flex; align-items: center; gap: 4px; min-height: 36px; font-size: 13px; }
.icon-action { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: 6px; color: var(--mv-text-muted); }
.icon-action:hover { background: var(--mv-panel); color: var(--mv-text); }
.delete:hover { color: #b91c1c; }
.parties-form { margin-top: 6px; padding: 12px; border: 1px solid var(--mv-border); border-radius: 8px; }
@media (max-width: 600px) {
  .contract-summary { grid-template-areas: "summary management" "links links"; grid-template-columns: minmax(0, 1fr) auto; align-items: start; }
  .contract-summary > :first-child { grid-area: summary; }
  .contract-actions { grid-area: links; gap: 0 8px; }
  .contract-management { grid-area: management; gap: 0; }
  .source, .icon-action, .parties-form button, .field-input { min-height: 44px; }
  .icon-action { width: 44px; }
  .form-actions { flex-wrap: wrap; }
}
</style>
