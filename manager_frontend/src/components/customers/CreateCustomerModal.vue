<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ManagerCatalogCustomerItemResponse } from '../../client';
import { api } from '../../api';
import { useBelarusPhoneMask } from '../../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../../composables/useB2BLookup';
import { getApiFieldError, parseApiFieldErrors } from '../../utils/api-errors';
import { normalizeUnp } from '../../utils/legal-requisites';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import LeadCustomerTypeChooser from '../leads/LeadCustomerTypeChooser.vue';
import {
  buildCustomerCreatePayload,
  defaultSigningMode,
  isBusinessCustomer,
  validateCustomerProfileForm,
  type CustomerForm,
  type CustomerPartyType,
} from './customer-profile-form';

const emit = defineEmits<{
  close: [];
  created: [customer: ManagerCatalogCustomerItemResponse];
  openExisting: [customerId: number];
}>();

const form = ref<CustomerForm>({
  name: '',
  phone: '',
  email: '',
  type: 'individual',
  city: '',
  inn: '',
  kpp: '',
  full_legal_name: '',
  legal_address: '',
  actual_address: '',
  bank_name: '',
  bic: '',
  iban: '',
  signer_position: '',
  signer_name: '',
  acting_basis: '',
  signing_mode: 'self',
});
const saving = ref(false);
const error = ref('');
const serverErrors = ref<Record<string, string>>({});
const duplicateCustomerId = ref<number | null>(null);
const phoneInputRef = ref<HTMLInputElement | null>(null);
const phoneModel = computed({
  get: () => form.value.phone,
  set: (value: string) => {
    form.value.phone = value;
  },
});
const phoneMask = useBelarusPhoneMask(phoneInputRef, phoneModel);
const { lookupCompany, isEgrLoading, egrError } = useB2BLookup();
const business = computed(() => isBusinessCustomer(form.value.type));

const inputClass = (field: keyof CustomerForm) => [
  'w-full rounded-xl border bg-slate-900 px-4 py-3 text-sm text-slate-100 outline-none transition-all placeholder:text-slate-600 focus:ring-2 focus:ring-teal-500 disabled:opacity-50',
  serverErrors.value[field] ? 'border-red-500/70' : 'border-slate-600 focus:border-transparent',
];

const setCustomerType = (type: CustomerPartyType) => {
  form.value = {
    ...form.value,
    type,
    signing_mode: defaultSigningMode(type),
  };
  serverErrors.value = { ...serverErrors.value, type: '' };
};

const handleInnBlur = async () => {
  form.value.inn = normalizeUnp(form.value.inn);
  if (form.value.inn.length !== 9) return;
  const company = await lookupCompany(form.value.inn);
  if (!company) return;
  form.value.full_legal_name = company.fullLegalName || form.value.full_legal_name;
  form.value.legal_address = company.legalAddress || form.value.legal_address;
  if (!form.value.name.trim()) {
    form.value.name = company.fullLegalName || '';
  }
};

const handleClose = () => {
  if (!saving.value) emit('close');
};

const handleCreate = async () => {
  serverErrors.value = {};
  error.value = '';
  duplicateCustomerId.value = null;
  const validation = validateCustomerProfileForm(
    form.value,
    phoneMask.isComplete.value,
  );
  if (!validation.valid) {
    serverErrors.value = { ...validation.fieldErrors };
    if (validation.phoneError) serverErrors.value.phone = validation.phoneError;
    if (validation.emailError) serverErrors.value.email = validation.emailError;
    if (validation.innError) serverErrors.value.inn = validation.innError;
    error.value = `Исправьте: ${validation.issues.join('; ')}`;
    return;
  }

  saving.value = true;
  try {
    const created = await api.createManagerCustomer(buildCustomerCreatePayload(form.value));
    emit('created', created);
  } catch (err) {
    const parsed = parseApiFieldErrors(err, [
      'name',
      'phone',
      'email',
      'type',
      'inn',
      'full_legal_name',
      'legal_address',
      'city',
    ]);
    serverErrors.value = parsed.fieldErrors;
    error.value = parsed.message;
    const duplicateId = Number(getApiFieldError(err, 'duplicate_customer_id'));
    duplicateCustomerId.value = Number.isFinite(duplicateId) && duplicateId > 0
      ? duplicateId
      : null;
  } finally {
    saving.value = false;
  }
};

watch(
  () => form.value.type,
  (type) => {
    if (!business.value) {
      form.value.signing_mode = defaultSigningMode(type);
    }
  },
);
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        class="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
        data-testid="create-customer-modal"
        @click.self="handleClose"
      >
        <section class="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-700/60 bg-[#1e293b] shadow-2xl">
          <header class="flex items-center justify-between border-b border-slate-700/50 px-6 py-4">
            <div>
              <h2 class="text-lg font-bold text-white">Новый клиент</h2>
              <p class="mt-0.5 text-xs text-slate-400">Для начала достаточно названия или ФИО</p>
            </div>
            <button type="button" class="text-slate-400 transition-colors hover:text-white" :disabled="saving" @click="handleClose">
              <span class="material-icons-round text-xl">close</span>
            </button>
          </header>

          <div class="space-y-5 overflow-y-auto px-6 py-5">
            <div>
              <label class="mb-2 block text-sm font-medium text-slate-300">Тип клиента</label>
              <LeadCustomerTypeChooser
                :model-value="form.type"
                :show-error="Boolean(serverErrors.type)"
                @update:model-value="setCustomerType"
              />
            </div>

            <div class="grid gap-4 sm:grid-cols-2">
              <label class="sm:col-span-2">
                <span class="mb-2 block text-sm font-medium text-slate-300">
                  {{ business ? 'Краткое название' : 'ФИО или название' }}
                  <span class="text-red-400">*</span>
                </span>
                <input
                  v-model="form.name"
                  data-testid="customer-name"
                  type="text"
                  :disabled="saving"
                  :class="inputClass('name')"
                  :placeholder="business ? 'Например, ООО МВН' : 'Например, Иван Иванов'"
                />
                <span v-if="serverErrors.name" class="mt-1 block text-xs text-red-300">{{ serverErrors.name }}</span>
              </label>

              <label>
                <span class="mb-2 block text-sm font-medium text-slate-300">Телефон <span class="font-normal text-slate-500">— необязательно</span></span>
                <input ref="phoneInputRef" v-model="form.phone" type="tel" :disabled="saving" :class="inputClass('phone')" placeholder="+375 (__) ___-__-__" />
                <span v-if="serverErrors.phone" class="mt-1 block text-xs text-red-300">{{ serverErrors.phone }}</span>
              </label>

              <label>
                <span class="mb-2 block text-sm font-medium text-slate-300">Email <span class="font-normal text-slate-500">— необязательно</span></span>
                <input v-model="form.email" type="email" :disabled="saving" :class="inputClass('email')" placeholder="client@example.com" />
                <span v-if="serverErrors.email" class="mt-1 block text-xs text-red-300">{{ serverErrors.email }}</span>
              </label>
            </div>

            <div v-if="business" class="space-y-4 rounded-xl border border-slate-700/60 bg-slate-900/35 p-4">
              <div class="relative">
                <label class="mb-2 block text-sm font-medium text-slate-300">УНП <span class="font-normal text-slate-500">— подставим реквизиты автоматически</span></label>
                <input v-model="form.inn" type="text" inputmode="numeric" maxlength="9" :disabled="saving" :class="inputClass('inn')" placeholder="123456789" @blur="handleInnBlur" />
                <span v-if="isEgrLoading" class="material-icons-round absolute bottom-3 right-3 animate-spin text-sm text-teal-400">refresh</span>
                <span v-if="serverErrors.inn" class="mt-1 block text-xs text-red-300">{{ serverErrors.inn }}</span>
                <span v-else-if="egrError" class="mt-1 block text-xs text-amber-300">{{ egrError }}</span>
              </div>
              <label>
                <span class="mb-2 block text-sm font-medium text-slate-300">Полное наименование</span>
                <input v-model="form.full_legal_name" type="text" :disabled="saving" :class="inputClass('full_legal_name')" placeholder="Заполнится по УНП или вручную" />
              </label>
              <AddressSuggestInput
                v-model="form.legal_address"
                placeholder="Юридический адрес"
                :input-class="inputClass('legal_address')"
                :error="serverErrors.legal_address"
              />
              <label>
                <span class="mb-2 block text-sm font-medium text-slate-300">Город</span>
                <input v-model="form.city" type="text" :disabled="saving" :class="inputClass('city')" placeholder="Например, Витебск" />
              </label>
            </div>

            <div v-if="error" class="rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-200">
              <p>{{ error }}</p>
              <button
                v-if="duplicateCustomerId"
                type="button"
                class="mt-3 rounded-lg border border-red-400/40 px-3 py-2 text-xs font-semibold transition-colors hover:bg-red-400/10"
                @click="emit('openExisting', duplicateCustomerId)"
              >Открыть существующего клиента</button>
            </div>
          </div>

          <footer class="flex justify-end gap-3 border-t border-slate-700/50 px-6 py-4">
            <button type="button" class="rounded-lg px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-40" :disabled="saving" @click="handleClose">Отмена</button>
            <button
              type="button"
              data-testid="submit-customer"
              class="flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-teal-900/30 transition-colors hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="saving || !form.name.trim()"
              @click="handleCreate"
            >
              <span v-if="saving" class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              <span v-else class="material-icons-round text-base">person_add</span>
              {{ saving ? 'Создаём…' : 'Создать и открыть карточку' }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
