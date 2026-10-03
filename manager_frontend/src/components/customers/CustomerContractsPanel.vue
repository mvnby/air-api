<script setup lang="ts">
import { toRef } from 'vue';
import { useCustomerContractsPanel } from './useCustomerContractsPanel';
const props = defineProps<{ customerId: number; openCreate?: boolean }>();
const { error, loadCustomerContracts, contracts, openContractUploadForm, openContractForm, showContractForm, createContract, contractForm, syncContractValidUntil, openContractTemplates, getTemplateRoleLabel, contractSaving, showContractUploadForm, uploadContract, contractUploadForm, syncUploadContractValidUntil, onContractUploadFileChange, contractUploadSaving, contractsLoading, formatDateOnly, getRoleLabel, archiveContract, deleteContract } = useCustomerContractsPanel(toRef(props, 'customerId'));
</script>
<template>
<section class="customer-section">
  <p v-if="error" role="alert" class="request-error">{{ error }} <button class="workspace-link" type="button" @click="loadCustomerContracts">Повторить</button></p>
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 class="flex items-center gap-2 text-lg font-bold">
              <span class="material-icons-round text-brand-500">contract</span>
              Открытые договоры
              <span v-if="contracts.length" class="flex h-6 min-w-6 items-center justify-center rounded-full bg-brand-500/20 px-2 text-xs text-brand-400">{{ contracts.length }}</span>
            </h2>
            <div class="flex flex-wrap gap-2">
              <button class="btn-mini-outline" type="button" @click="openContractUploadForm">
                Загрузить договор
              </button>
              <button class="btn-mini" type="button" @click="openContractForm">
                Создать договор
              </button>
            </div>
          </div>

          <form v-if="showContractForm" class="mb-4 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="createContract">
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

          <form v-if="showContractUploadForm" class="mb-4 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="uploadContract">
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

          <div v-if="contractsLoading" class="text-sm text-[var(--mv-text-muted)] p-5 border border-dashed border-[var(--mv-border)] rounded-2xl">
            Загрузка договоров...
          </div>
          <div v-else-if="contracts.length" class="space-y-3">
            <div v-for="contract in contracts" :key="contract.id" class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-[#1e293b] dark:text-slate-300">
              <div class="flex items-center gap-4">
                <div class="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-brand-600 dark:bg-slate-800 dark:text-brand-400">
                  <span class="material-icons-round text-2xl">article</span>
                </div>
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <p class="text-[15px] font-semibold leading-none text-slate-900 dark:text-white">{{ contract.number }}</p>
                    <span class="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider" :class="contract.status === 'active' ? 'bg-brand-500/10 text-brand-700 dark:text-brand-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'">
                      {{ contract.status === 'active' ? 'активен' : 'архив' }}
                    </span>
                  </div>
                  <p class="mt-2 text-[13px] leading-none text-slate-500 dark:text-slate-400">
                    {{ formatDateOnly(contract.valid_from) }} - {{ formatDateOnly(contract.valid_until) }}
                  </p>
                  <p class="mt-2 text-[12px] leading-none text-slate-500 dark:text-slate-400">
                    Роли: {{ getRoleLabel(contract.document_role_type) }}
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <a v-if="contract.edit_url" :href="contract.edit_url" target="_blank" class="flex h-10 w-10 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white" title="Открыть договор">
                  <span class="material-icons-round text-[20px]">open_in_new</span>
                </a>
                <button v-if="contract.status === 'active'" class="flex h-10 w-10 items-center justify-center rounded-lg text-amber-400 hover:bg-amber-500/10 hover:text-amber-300 transition-colors" type="button" title="Архивировать" @click="archiveContract(contract)">
                  <span class="material-icons-round text-[20px]">archive</span>
                </button>
                <button class="flex h-10 w-10 items-center justify-center rounded-lg text-red-400 transition-colors hover:bg-red-500/10 hover:text-red-300" type="button" title="Удалить" @click="deleteContract(contract)">
                  <span class="material-icons-round text-[20px]">delete</span>
                </button>
              </div>
            </div>
          </div>
          <div v-else-if="!error" class="text-sm text-[var(--mv-text-muted)] italic py-5 text-center rounded-2xl border border-dashed border-[var(--mv-border)]">
            Открытые договоры пока не созданы
          </div>
        </section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
