<script setup lang="ts">
import { toRef } from 'vue';
import { Archive, ExternalLink, Trash2 } from 'lucide-vue-next';
import { useCustomerContractsPanel } from './useCustomerContractsPanel';
const props = defineProps<{ customerId: number; openCreate?: boolean }>();
const { error, loadCustomerContracts, contracts, openContractUploadForm, openContractForm, showContractForm, createContract, contractForm, syncContractValidUntil, openContractTemplates, getTemplateRoleLabel, contractSaving, showContractUploadForm, uploadContract, contractUploadForm, syncUploadContractValidUntil, onContractUploadFileChange, contractUploadSaving, contractsLoading, formatDateOnly, getRoleLabel, archiveContract, deleteContract } = useCustomerContractsPanel(toRef(props, 'customerId'));
</script>
<template>
<section class="customer-section">
  <p v-if="error" role="alert" class="request-error">{{ error }} <button class="workspace-link" type="button" @click="loadCustomerContracts">Повторить</button></p>
  <div class="contracts-heading">
    <h2>Открытые договоры <span v-if="contracts.length" class="muted">{{ contracts.length }}</span></h2>
    <div class="contracts-actions">
      <button class="btn-mini-outline" type="button" aria-label="Загрузить договор" @click="openContractUploadForm">Загрузить</button>
      <button class="btn-mini" type="button" aria-label="Создать договор" @click="openContractForm">Создать</button>
    </div>
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

  <p v-if="contractsLoading" class="contracts-state">Загрузка договоров…</p>
  <div v-else-if="contracts.length" class="contracts-list">
    <div v-for="contract in contracts" :key="contract.id" class="contract-row">
      <div class="contract-info">
        <div class="contract-title">
          <span>{{ contract.number }}</span>
          <span class="badge">{{ contract.status === 'active' ? 'Активен' : 'Архив' }}</span>
        </div>
        <p class="contract-detail">{{ formatDateOnly(contract.valid_from) }} — {{ formatDateOnly(contract.valid_until) }} · {{ getRoleLabel(contract.document_role_type) }}</p>
      </div>
      <div class="contracts-actions">
        <a v-if="contract.edit_url" :href="contract.edit_url" target="_blank" rel="noopener noreferrer" class="contract-action" aria-label="Открыть договор" title="Открыть договор"><ExternalLink :size="16" /></a>
        <button v-if="contract.status === 'active'" class="contract-action" type="button" aria-label="Архивировать договор" title="Архивировать" @click="archiveContract(contract)"><Archive :size="16" /></button>
        <button class="contract-action contract-delete" type="button" aria-label="Удалить договор" title="Удалить" @click="deleteContract(contract)"><Trash2 :size="16" /></button>
      </div>
    </div>
  </div>
  <p v-else-if="!error" class="contracts-state">Открытые договоры пока не созданы</p>
</section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.contracts-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; }
.contracts-heading h2 { margin: 0; font-size: 14px; font-weight: 600; }
.contracts-heading h2 span { margin-left: 4px; font-size: 12px; font-weight: 400; }
.contracts-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.contracts-heading button { font-size: 12px; }
.contracts-state { margin: 8px 0 0; color: var(--mv-text-muted); font-size: 12px; }
.contracts-list { margin-top: 6px; }
.contract-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--mv-border); }
.contract-info { min-width: 0; }
.contract-title { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }
.contract-detail { margin-top: 3px; color: var(--mv-text-muted); font-size: 12px; }
.contract-action { display: inline-flex; align-items: center; justify-content: center; min-width: 32px; min-height: 32px; border-radius: 6px; color: var(--mv-text-muted); }
.contract-action:hover { background: var(--mv-panel); color: var(--mv-text); }
.contract-delete { color: #b91c1c; }
:global(.dark) .contract-delete { color: #fca5a5; }
</style>
