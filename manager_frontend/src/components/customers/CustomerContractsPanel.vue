<script setup lang="ts">
import { computed, toRef } from 'vue';
import { hasManagerCapability, MANAGER_CAPABILITY } from '../../manager-capabilities';
import { managerSession } from '../../services/manager-session';
import { useCustomerContractsPanel } from './useCustomerContractsPanel';
import CustomerContractRow from './CustomerContractRow.vue';

const props = defineProps<{ customerId: number; orderCount: number; ordersUrl: string; editContractId?: number }>();
const emit = defineEmits<{ openOrders: []; createOrder: [] }>();
const canManage = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.crmManage)
  && !managerSession.auth.value?.demo_read_only);
const {
  error, loadCustomerContracts, contracts, openContractUploadForm, openContractForm, showContractForm,
  createContract, contractForm, syncContractValidUntil, openContractTemplates, getTemplateRoleLabel,
  contractSaving, showContractUploadForm, uploadContract, contractUploadForm, syncUploadContractValidUntil,
  onContractUploadFileChange, contractUploadSaving, contractsLoading, archiveContract, deleteContract,
  issuers, issuersLoading, issuersError, loadIssuers,
} = useCustomerContractsPanel(toRef(props, 'customerId'));
</script>
<template>
<section class="customer-panel" data-testid="customer-contract-register">
  <p v-if="error" role="alert" class="request-error">{{ error }} <button class="workspace-link" type="button" @click="loadCustomerContracts">Повторить</button></p>
  <div class="contracts-heading">
    <h2>Открытые договоры <span v-if="contracts.length" class="muted">{{ contracts.length }}</span></h2>
    <button v-if="canManage" class="btn-mini" type="button" @click="orderCount > 0 ? emit('openOrders') : emit('createOrder')">{{ orderCount > 0 ? 'Выбрать заказ' : 'Создать заказ' }}</button>
  </div>
  <p v-if="canManage" class="contracts-help">В заказе откройте «Документы» → «Договор» → «Рамочный договор».</p>

  <details v-if="canManage" class="legacy-tools" :open="showContractForm || showContractUploadForm">
    <summary>Договоры Google</summary>
    <div class="legacy-actions">
      <button class="btn-mini-outline" type="button" @click="openContractForm">Создать в Google Docs</button>
      <button class="btn-mini-outline" type="button" @click="openContractUploadForm">Загрузить в Google Drive</button>
    </div>

  <form v-if="showContractForm" class="mt-2 mb-3 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="createContract">
    <div class="grid gap-3 md:grid-cols-4">
      <input v-model="contractForm.number" class="field-input" type="text" placeholder="Номер, если уже известен" />
      <input v-model="contractForm.contract_date" class="field-input" type="date" @change="syncContractValidUntil" />
      <input v-model="contractForm.valid_until" class="field-input" type="date" />
      <select v-model="contractForm.template_id" class="field-input">
        <option v-for="template in openContractTemplates" :key="template.id" :value="template.id">
          {{ template.name }}
        </option>
      </select>
      <p class="md:col-span-4 text-xs text-[var(--mv-text-muted)]">
        Роли берутся из выбранного шаблона: {{ getTemplateRoleLabel(contractForm.template_id) }}
      </p>
    </div>
    <div class="mt-3 flex justify-end gap-2">
      <button class="btn-mini-outline" type="button" @click="showContractForm = false">Отмена</button>
      <button class="btn-mini" type="submit" :disabled="contractSaving">
        {{ contractSaving ? 'Создаем...' : 'Создать' }}
      </button>
    </div>
  </form>

  <form v-if="showContractUploadForm" class="mt-2 mb-3 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="uploadContract">
    <div class="grid gap-3 md:grid-cols-4">
      <input v-model="contractUploadForm.number" class="field-input" type="text" placeholder="Номер договора" required />
      <input v-model="contractUploadForm.contract_date" class="field-input" type="date" required @change="syncUploadContractValidUntil" />
      <input v-model="contractUploadForm.valid_until" class="field-input" type="date" required />
      <select v-model="contractUploadForm.template_id" class="field-input">
        <option v-for="template in openContractTemplates" :key="template.id" :value="template.id">
          {{ template.name }}
        </option>
      </select>
      <input class="field-input" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required @change="onContractUploadFileChange" />
      <p class="md:col-span-4 text-xs text-[var(--mv-text-muted)]">
        Роли загруженного договора будут взяты из выбранного шаблона: {{ getTemplateRoleLabel(contractUploadForm.template_id) }}
      </p>
    </div>
    <div class="mt-3 flex justify-end gap-2">
      <button class="btn-mini-outline" type="button" @click="showContractUploadForm = false">Отмена</button>
      <button class="btn-mini" type="submit" :disabled="contractUploadSaving">
        {{ contractUploadSaving ? 'Загружаем...' : 'Загрузить' }}
      </button>
    </div>
  </form>

  </details>

  <p v-if="contractsLoading" class="contracts-state">Загрузка договоров…</p>
  <ul v-else-if="contracts.length" class="contracts-list">
    <CustomerContractRow v-for="contract in contracts" :key="contract.id" :contract="contract" :issuers="issuers"
      :issuers-loading="issuersLoading" :issuers-error="issuersError" :can-manage="canManage" :orders-url="ordersUrl" :edit-initially="contract.id === editContractId"
      @saved="loadCustomerContracts" @retry-issuers="loadIssuers" @archive="archiveContract" @delete="deleteContract" />
  </ul>
  <p v-else-if="!error" class="contracts-state">Открытые договоры пока не созданы</p>
</section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.contracts-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; }
.contracts-heading h2 { margin: 0; font-size: 14px; font-weight: 600; }
.contracts-heading h2 span { margin-left: 4px; font-size: 12px; font-weight: 400; }
.contracts-list { margin-top: 12px; }
.contracts-state, .contracts-help { margin: 8px 0 0; color: var(--mv-text-muted); font-size: 13px; }
.legacy-tools { margin-top: 10px; }
.legacy-tools summary { width: fit-content; cursor: pointer; font-size: 13px; color: var(--kitlane-accent-text); }
.legacy-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
@media (max-width: 600px) { .contracts-heading button, .legacy-actions button, .legacy-tools summary { min-height: 44px; } .legacy-tools summary { align-content: center; } }
</style>
