<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { ArrowLeft, Building2, Mail, Phone, ReceiptText, Save, UserRound, X } from 'lucide-vue-next';
import { api } from '../api';
import { ManagerService, type ManagerCatalogCustomerItemResponse, type ManagerCustomerDocumentItem } from '../client';
import { useBelarusPhoneMask } from '../composables/useBelarusPhoneMask';
import { dispatchCustomerUpdated } from '../utils/customer-events';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';
import { normalizeIban, normalizeUnp } from '../utils/legal-requisites';
import { normalizePhoneForApi } from '../utils/phone';
import {
  normalizeEmail,
  validateOptionalBelarusPhone,
  validateOptionalByIban,
  validateOptionalByUnp,
  validateOptionalEmail,
} from '../utils/validation';

type CustomerForm = {
  name: string;
  phone: string;
  email: string;
  type: 'individual' | 'company';
  inn: string;
  kpp: string;
  full_legal_name: string;
  legal_address: string;
  actual_address: string;
  bank_name: string;
  bic: string;
  iban: string;
  signer_position: string;
  signer_name: string;
  acting_basis: string;
};

const customer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const saveError = ref('');
const success = ref('');
const editMode = ref(false);
const serverErrors = ref<Record<string, string>>({});

const documents = ref<ManagerCustomerDocumentItem[]>([]);
const docsLoading = ref(false);

const phoneError = ref('');
const emailError = ref('');
const innError = ref('');
const ibanError = ref('');
const phoneInputRef = ref<HTMLInputElement | null>(null);

const form = ref<CustomerForm>({
  name: '',
  phone: '',
  email: '',
  type: 'individual',
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
});

const phoneModel = computed({
  get: () => form.value.phone,
  set: (value: string) => {
    form.value.phone = value;
  },
});

const phoneMask = useBelarusPhoneMask(phoneInputRef, phoneModel);

const customerId = computed(() => {
  const raw = new URLSearchParams(window.location.search).get('customerId');
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
});

const returnTo = computed(() => new URLSearchParams(window.location.search).get('returnTo') || '');
const backLabel = computed(() => (returnTo.value ? 'Назад' : 'К списку клиентов'));

const formatDate = (iso?: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
};

const toForm = (item: ManagerCatalogCustomerItemResponse): CustomerForm => ({
  name: item.name || '',
  phone: item.phone || '',
  email: item.email || '',
  type: item.type === 'company' ? 'company' : 'individual',
  inn: item.inn || '',
  kpp: item.kpp || '',
  full_legal_name: item.full_legal_name || '',
  legal_address: item.legal_address || '',
  actual_address: item.actual_address || '',
  bank_name: item.bank_name || '',
  bic: item.bic || '',
  iban: item.iban || '',
  signer_position: item.signer_position || '',
  signer_name: item.signer_name || '',
  acting_basis: item.acting_basis || '',
});

const currentForm = computed(() => form.value);

const formDiff = computed<Record<keyof CustomerForm, boolean>>(() => {
  const source = customer.value;
  if (!source) return {} as Record<keyof CustomerForm, boolean>;
  const original = toForm(source);
  const entries = Object.keys(original) as (keyof CustomerForm)[];
  const diff: Partial<Record<keyof CustomerForm, boolean>> = {};
  for (const key of entries) {
    diff[key] = (original[key] || '').toString().trim() !== (currentForm.value[key] || '').toString().trim();
  }
  return diff as Record<keyof CustomerForm, boolean>;
});

const hasChanges = computed(() => Object.values(formDiff.value).some(Boolean));
const isCompany = computed(() => currentForm.value.type === 'company');

const fieldClass = (key: keyof CustomerForm) => ({
  'field-input': true,
  changed: formDiff.value[key],
  'border-red-500 focus:outline-red-400':
    Boolean(serverErrors.value[key]) ||
    (key === 'phone' && Boolean(phoneError.value)) ||
    (key === 'email' && Boolean(emailError.value)) ||
    (key === 'inn' && Boolean(innError.value)) ||
    (key === 'iban' && Boolean(ibanError.value)),
});

const clearFieldErrors = () => {
  serverErrors.value = {};
  phoneError.value = '';
  emailError.value = '';
  innError.value = '';
  ibanError.value = '';
};

const resetFormFromCustomer = () => {
  if (!customer.value) return;
  form.value = toForm(customer.value);
  clearFieldErrors();
};

const loadCustomer = async () => {
  if (!customerId.value) {
    error.value = 'Не передан customerId';
    customer.value = null;
    return;
  }
  loading.value = true;
  error.value = '';
  saveError.value = '';
  success.value = '';
  try {
    customer.value = await api.getManagerCustomerDetail(customerId.value);
    resetFormFromCustomer();
  } catch (e) {
    console.error(e);
    error.value = `Не удалось загрузить карточку клиента: ${getApiErrorMessage(e)}`;
    customer.value = null;
  } finally {
    loading.value = false;
  }
};

const loadCustomerDocs = async () => {
  if (!customerId.value) return;
  docsLoading.value = true;
  try {
    const res = await ManagerService.getManagerCustomerDocs(customerId.value);
    documents.value = res.items;
  } catch (e) {
    console.error('Failed to load customer docs', e);
  } finally {
    docsLoading.value = false;
  }
};

const navigateToCustomers = () => {
  const target = returnTo.value || '/manager/customers';
  window.history.pushState({}, '', target);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const openOrders = () => {
  if (!customer.value) return;
  const search = customer.value.inn || customer.value.phone || customer.value.email || customer.value.name || '';
  const path = search
    ? `/manager/orders/kanban?search=${encodeURIComponent(search)}`
    : '/manager/orders/kanban';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const startEdit = () => {
  if (!customer.value) return;
  editMode.value = true;
  success.value = '';
  saveError.value = '';
  resetFormFromCustomer();
};

const cancelEdit = () => {
  editMode.value = false;
  resetFormFromCustomer();
};

const normalizeForm = () => {
  form.value.email = normalizeEmail(form.value.email || '');
  form.value.inn = normalizeUnp(form.value.inn || '');
  form.value.iban = normalizeIban(form.value.iban || '');
};

const validateForm = (): boolean => {
  normalizeForm();
  clearFieldErrors();

  phoneError.value = validateOptionalBelarusPhone(form.value.phone || '', phoneMask.isComplete.value);
  emailError.value = validateOptionalEmail(form.value.email || '');
  innError.value = validateOptionalByUnp(form.value.inn || '');
  ibanError.value = validateOptionalByIban(form.value.iban || '');

  if (!form.value.name.trim()) {
    serverErrors.value.name = 'Имя клиента не может быть пустым';
  }
  if (!form.value.phone.trim()) {
    phoneError.value = 'Телефон обязателен';
  }
  if (isCompany.value && !form.value.full_legal_name.trim()) {
    serverErrors.value.full_legal_name = 'Для юрлица укажите полное наименование';
  }

  return !phoneError.value && !emailError.value && !innError.value && !ibanError.value && !Object.keys(serverErrors.value).length;
};

const saveCustomer = async () => {
  if (!customer.value || !hasChanges.value || !validateForm()) return;

  const payload: Record<string, string> = {};
  (Object.keys(formDiff.value) as (keyof CustomerForm)[]).forEach((key) => {
    if (!formDiff.value[key]) return;
    payload[key] = currentForm.value[key]?.trim?.() ?? currentForm.value[key];
  });

  payload.phone = normalizePhoneForApi(form.value.phone || '');
  payload.email = normalizeEmail(form.value.email || '');
  payload.inn = normalizeUnp(form.value.inn || '');
  payload.iban = normalizeIban(form.value.iban || '');

  const optionalKeys: (keyof CustomerForm)[] = [
    'email',
    'inn',
    'kpp',
    'full_legal_name',
    'legal_address',
    'actual_address',
    'bank_name',
    'bic',
    'iban',
    'signer_position',
    'signer_name',
    'acting_basis',
  ];
  optionalKeys.forEach((key) => {
    if (!(key in payload)) return;
    if (!payload[key]) payload[key] = '';
  });

  saving.value = true;
  success.value = '';
  saveError.value = '';
  try {
    const updated = await api.patchManagerCustomer(customer.value.id, payload);
    customer.value = updated;
    editMode.value = false;
    resetFormFromCustomer();
    success.value = 'Карточка клиента обновлена';
    dispatchCustomerUpdated(updated);
  } catch (e) {
    console.error(e);
    const parsed = parseApiFieldErrors(e, [
      'name',
      'phone',
      'email',
      'type',
      'inn',
      'kpp',
      'full_legal_name',
      'legal_address',
      'actual_address',
      'bank_name',
      'bic',
      'iban',
      'signer_position',
      'signer_name',
      'acting_basis',
    ]);
    serverErrors.value = parsed.fieldErrors;
    if (!phoneError.value && parsed.fieldErrors.phone) phoneError.value = parsed.fieldErrors.phone;
    if (!emailError.value && parsed.fieldErrors.email) emailError.value = parsed.fieldErrors.email;
    if (!innError.value && parsed.fieldErrors.inn) innError.value = parsed.fieldErrors.inn;
    if (!ibanError.value && parsed.fieldErrors.iban) ibanError.value = parsed.fieldErrors.iban;
    saveError.value = `Не удалось сохранить карточку клиента: ${parsed.message}`;
  } finally {
    saving.value = false;
  }
};

watch(customerId, () => {
  void loadCustomer();
  void loadCustomerDocs();
});

onMounted(() => {
  void loadCustomer();
  void loadCustomerDocs();
});
</script>

<template>
  <div class="min-h-screen bg-[var(--mv-bg)] text-[var(--mv-text)]">
    <div class="mx-auto max-w-[1200px] px-4 py-6 md:px-8">
      <div class="mb-4 flex items-center gap-2">
        <button class="btn-mini-outline" type="button" @click="navigateToCustomers">
          <ArrowLeft class="h-4 w-4" />
          {{ backLabel }}
        </button>
        <button v-if="customer" class="btn-mini" type="button" @click="openOrders">
          Сделки клиента
        </button>
        <button v-if="customer && !editMode" class="btn-mini" type="button" @click="startEdit">
          Редактировать
        </button>
        <button v-if="customer && editMode" class="btn-mini-outline" type="button" :disabled="saving" @click="cancelEdit">
          <X class="h-4 w-4" />
          Отмена
        </button>
        <button v-if="customer && editMode" class="btn-mini" type="button" :disabled="saving || !hasChanges" @click="saveCustomer">
          <Save class="h-4 w-4" />
          {{ saving ? 'Сохраняем…' : 'Сохранить' }}
        </button>
      </div>

      <div v-if="loading" class="rounded-[2rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-8 text-sm text-[var(--mv-text-muted)]">
        Загрузка карточки клиента...
      </div>
      <div v-else-if="error" class="rounded-[2rem] border border-red-500/40 bg-red-900/20 p-6 text-sm text-red-200">
        {{ error }}
      </div>
      <div v-else-if="customer" class="space-y-4">
        <div v-if="success" class="rounded-xl border border-emerald-500/40 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-200">
          {{ success }}
        </div>
        <div v-if="saveError" class="rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-200">
          {{ saveError }}
        </div>

        <header class="rounded-[2rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-6 shadow-sm">
          <p class="text-xs uppercase tracking-[0.2em] text-[var(--mv-text-muted)]">Customer profile</p>
          <h1 class="mt-2 text-2xl font-bold">{{ customer.full_legal_name || customer.name || `Клиент #${customer.id}` }}</h1>
          <p class="mt-1 text-sm text-[var(--mv-text-muted)]">ID: #{{ customer.id }} · {{ customer.type === 'company' ? 'Юр. лицо' : 'Физ. лицо' }}</p>
        </header>

        <section class="grid gap-4 md:grid-cols-2">
          <article class="rounded-[1.5rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-5 shadow-sm">
            <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[var(--mv-text-muted)]">Контакты</h2>

            <template v-if="!editMode">
              <div class="space-y-2 text-sm">
                <p class="detail"><UserRound class="h-4 w-4" /> <span>{{ customer.name || '—' }}</span></p>
                <p class="detail"><Phone class="h-4 w-4" /> <span>{{ customer.phone || '—' }}</span></p>
                <p class="detail"><Mail class="h-4 w-4" /> <span>{{ customer.email || '—' }}</span></p>
                <p class="detail"><Building2 class="h-4 w-4" /> <span>УНП: {{ customer.inn || '—' }}</span></p>
                <p class="detail"><Building2 class="h-4 w-4" /> <span>КПП: {{ customer.kpp || '—' }}</span></p>
                <p class="detail"><ReceiptText class="h-4 w-4" /> <span>Заказов: {{ customer.order_count }}</span></p>
                <p class="detail"><ReceiptText class="h-4 w-4" /> <span>Создан: {{ formatDate(customer.created_at) }}</span></p>
              </div>
            </template>

            <template v-else>
              <div class="space-y-3 text-sm">
                <select v-model="form.type" :class="fieldClass('type')">
                  <option value="individual">Физ. лицо</option>
                  <option value="company">Юр. лицо</option>
                </select>
                <input v-model="form.name" type="text" placeholder="Имя/Компания" :class="fieldClass('name')" />
                <input ref="phoneInputRef" v-model="form.phone" type="tel" placeholder="+375 (XX) XXX-XX-XX" :class="fieldClass('phone')" />
                <span v-if="phoneError" class="field-error">{{ phoneError }}</span>
                <input v-model="form.email" type="email" placeholder="Email" :class="fieldClass('email')" />
                <span v-if="emailError" class="field-error">{{ emailError }}</span>
                <input v-model="form.inn" type="text" placeholder="УНП" :class="fieldClass('inn')" />
                <span v-if="innError" class="field-error">{{ innError }}</span>
                <input v-model="form.kpp" type="text" placeholder="КПП" :class="fieldClass('kpp')" />
              </div>
            </template>
          </article>

          <article class="rounded-[1.5rem] border border-[var(--mv-border)] bg-[var(--mv-surface)] p-5 shadow-sm">
            <h2 class="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-[var(--mv-text-muted)]">Юр. реквизиты</h2>

            <template v-if="!editMode">
              <div class="space-y-2 text-sm">
                <p class="detail-value"><span>Полное наименование</span><strong>{{ customer.full_legal_name || '—' }}</strong></p>
                <p class="detail-value"><span>Юр. адрес</span><strong>{{ customer.legal_address || '—' }}</strong></p>
                <p class="detail-value"><span>Факт. адрес</span><strong>{{ customer.actual_address || '—' }}</strong></p>
                <p class="detail-value"><span>Банк</span><strong>{{ customer.bank_name || '—' }}</strong></p>
                <p class="detail-value"><span>BIC</span><strong>{{ customer.bic || '—' }}</strong></p>
                <p class="detail-value"><span>IBAN</span><strong>{{ customer.iban || '—' }}</strong></p>
                <p class="detail-value"><span>Подписант</span><strong>{{ customer.signer_name || '—' }}</strong></p>
                <p class="detail-value"><span>Должность</span><strong>{{ customer.signer_position || '—' }}</strong></p>
                <p class="detail-value"><span>Основание</span><strong>{{ customer.acting_basis || '—' }}</strong></p>
                <p class="detail-value"><span>Последний адрес доставки</span><strong>{{ customer.last_delivery_address || '—' }}</strong></p>
              </div>
            </template>

            <template v-else>
              <div class="space-y-3 text-sm">
                <div v-if="isCompany" class="space-y-3">
                  <input v-model="form.full_legal_name" type="text" placeholder="Полное наименование" :class="fieldClass('full_legal_name')" />
                  <input v-model="form.legal_address" type="text" placeholder="Юр. адрес" :class="fieldClass('legal_address')" />
                  <input v-model="form.actual_address" type="text" placeholder="Факт. адрес" :class="fieldClass('actual_address')" />
                  <input v-model="form.bank_name" type="text" placeholder="Название банка" :class="fieldClass('bank_name')" />
                  <input v-model="form.bic" type="text" placeholder="BIC" :class="fieldClass('bic')" />
                  <input v-model="form.iban" type="text" placeholder="IBAN" :class="fieldClass('iban')" />
                  <span v-if="ibanError" class="field-error">{{ ibanError }}</span>
                  <input v-model="form.signer_name" type="text" placeholder="Подписант" :class="fieldClass('signer_name')" />
                  <input v-model="form.signer_position" type="text" placeholder="Должность подписанта" :class="fieldClass('signer_position')" />
                  <input v-model="form.acting_basis" type="text" placeholder="Основание действий" :class="fieldClass('acting_basis')" />
                </div>
                <p v-else class="text-xs text-[var(--mv-text-muted)]">Для физлица реквизиты юрлица не обязательны.</p>
              </div>
            </template>
          </article>
        </section>

        <section v-if="!editMode" class="mt-8 mb-6">
          <h2 class="mb-4 flex items-center gap-2 text-lg font-bold">
            <span class="material-icons-round text-teal-500">folder</span>
            Связанные документы 
            <span v-if="documents.length" class="flex h-6 w-6 items-center justify-center rounded-full bg-teal-500/20 text-xs text-teal-400">{{ documents.length }}</span>
          </h2>

          <div v-if="docsLoading" class="text-sm text-[var(--mv-text-muted)] p-5 border border-dashed border-[var(--mv-border)] rounded-2xl">
            Загрузка документов...
          </div>
          <div v-else-if="documents.length" class="space-y-3">
             <div v-for="doc in documents" :key="doc.id" class="flex items-center justify-between rounded-xl border border-slate-700/50 bg-[#1e293b] p-4 text-slate-300 shadow-sm">
                <div class="flex items-center gap-4">
                    <div class="flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-teal-400">
                      <span class="material-icons-round text-2xl">description</span>
                    </div>
                    <div>
                        <div class="flex items-center gap-2 mb-1">
                          <p class="text-[15px] font-semibold text-white leading-none">{{ doc.number || doc.doc_type }}</p>
                          <a :href="`/manager/orders/kanban?orderId=${doc.order_id}`" target="_blank" class="rounded bg-teal-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-teal-400 border border-teal-500/20 hover:bg-teal-500/20 hover:text-white transition-colors">Заказ #{{ doc.order_id }}</a>
                        </div>
                        <p class="text-[13px] text-slate-400 leading-none mt-1">{{ new Date(doc.date).toLocaleDateString('ru-RU', { year: 'numeric', month: 'long', day: 'numeric' }) }} · <span class="uppercase font-medium text-slate-300">{{ doc.doc_type }}</span></p>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <a :href="doc.edit_url" target="_blank" class="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white transition-colors" title="Открыть документ">
                        <span class="material-icons-round text-[20px]">open_in_new</span>
                    </a>
                </div>
            </div>
          </div>
          <div v-else class="text-sm text-[var(--mv-text-muted)] italic py-5 text-center rounded-2xl border border-dashed border-[var(--mv-border)]">
              Документы пока не найдены
          </div>
        </section>

      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--mv-text-muted);
}

.detail-value {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.detail-value span {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mv-text-muted);
}

.detail-value strong {
  color: var(--mv-text);
  font-weight: 600;
  word-break: break-word;
}

.field-input {
  width: 100%;
  border-radius: 0.8rem;
  border: 1px solid var(--mv-border);
  background: var(--mv-surface);
  color: var(--mv-text);
  padding: 0.55rem 0.75rem;
}

.field-input.changed {
  border-color: rgb(20 184 166);
  box-shadow: inset 0 0 0 1px rgb(20 184 166 / 0.3);
}

.field-error {
  margin-top: -0.35rem;
  display: block;
  font-size: 0.72rem;
  color: rgb(252 165 165);
}
</style>
