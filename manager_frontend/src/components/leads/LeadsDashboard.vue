<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
import type {
  LeadCreatePayload,
  LeadLossPayload,
  LeadQualifyPayload,
  LeadResponse,
  LeadUpdatePayload,
} from '../../client';
import { useBelarusPhoneMask } from '../../composables/useBelarusPhoneMask';
import { fromLocalDateTimeInput } from '../../utils/datetime';
import { isBelarusPhoneComplete, normalizePhoneForApi } from '../../utils/phone';

type LeadTab = '' | 'new' | 'contacted' | 'qualified' | 'lost' | 'spam';

const leads = ref<LeadResponse[]>([]);
const loading = ref(false);
const saving = ref(false);
const toast = ref('');
const search = ref('');
const source = ref('');
const overdueOnly = ref(false);
const includeArchived = ref(false);
const sort = ref('created_at_desc');
const statusTab = ref<LeadTab>('');

const showCreateModal = ref(false);
const showQualifyModal = ref(false);
const selectedLead = ref<LeadResponse | null>(null);
const createPhoneError = ref('');
const qualifyPhoneError = ref('');
const createPhoneInputRef = ref<HTMLInputElement | null>(null);
const qualifyPhoneInputRef = ref<HTMLInputElement | null>(null);

const createForm = ref<LeadCreatePayload>({
  source: 'manager',
  request_text: '',
  name: '',
  phone: '',
  email: '',
  inn: '',
  company_name: '',
  next_followup_date: undefined,
});

const qualifyForm = ref<LeadQualifyPayload>({
  name: '',
  phone: '',
  email: '',
  inn: '',
  full_legal_name: '',
  delivery_address: '',
  order_comment: '',
});

const createPhoneModel = computed({
  get: () => createForm.value.phone ?? '',
  set: (value: string) => {
    createForm.value.phone = value;
  },
});

const qualifyPhoneModel = computed({
  get: () => qualifyForm.value.phone ?? '',
  set: (value: string) => {
    qualifyForm.value.phone = value;
  },
});

const createPhoneMask = useBelarusPhoneMask(createPhoneInputRef, createPhoneModel);
const qualifyPhoneMask = useBelarusPhoneMask(qualifyPhoneInputRef, qualifyPhoneModel);

const statusLabels: Record<string, string> = {
  new: 'Новый',
  contacted: 'Связались',
  qualified: 'Квалифицирован',
  lost: 'Отказ',
  spam: 'Спам',
};

const sourceLabels: Record<string, string> = {
  phone: 'Телефон',
  site: 'Сайт',
  bot: 'Бот',
  email: 'Email',
  manager: 'Менеджер',
  other: 'Другое',
};

const segmentLabels: Record<string, string> = {
  unknown: 'Не определен',
  b2c: 'B2C',
  b2b: 'B2B',
};

const tabItems = computed(() => [
  { key: '', label: 'Активные' },
  { key: 'new', label: 'Новые' },
  { key: 'contacted', label: 'Связались' },
  { key: 'qualified', label: 'Квалифицированы' },
  { key: 'lost', label: 'Отказы' },
  { key: 'spam', label: 'Спам' },
]);

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU');
};

const isOverdue = (lead: LeadResponse) => {
  if (!lead.next_followup_date) return false;
  return new Date(lead.next_followup_date).getTime() < Date.now();
};

const getErrorMessage = (error: unknown): string => {
  const maybe = error as { body?: { detail?: unknown }; status?: number; message?: string; statusText?: string };
  const detail = maybe?.body?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    if (first?.msg) {
      const loc = Array.isArray(first.loc) ? first.loc.join('.') : '';
      return loc ? `${loc}: ${first.msg}` : first.msg;
    }
    return JSON.stringify(detail);
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail);
  if (maybe?.message) return maybe.message;
  if (maybe?.status) return `HTTP ${maybe.status}${maybe.statusText ? ` ${maybe.statusText}` : ''}`;
  return 'Неизвестная ошибка';
};

const loadLeads = async () => {
  loading.value = true;
  try {
    const response = await api.getManagerLeads({
      page: 1,
      limit: 100,
      status: statusTab.value || undefined,
      source: source.value || undefined,
      search: search.value || undefined,
      overdueOnly: overdueOnly.value,
      includeArchived: includeArchived.value,
      sort: sort.value,
    });
    leads.value = response.items;
  } catch (error) {
    console.error(error);
    setToast(`Не удалось загрузить лиды: ${getErrorMessage(error)}`);
  } finally {
    loading.value = false;
  }
};

const resetCreateForm = () => {
  createForm.value = {
    source: 'manager',
    request_text: '',
    name: '',
    phone: '',
    email: '',
    inn: '',
    company_name: '',
    next_followup_date: undefined,
  };
  createPhoneError.value = '';
};

const getPhoneValidationError = (
  value: string | null | undefined,
  isComplete: boolean,
): string => {
  const raw = (value || '').trim();
  if (!raw) {
    return '';
  }
  if (!isComplete || !isBelarusPhoneComplete(raw)) {
    return 'Введите телефон полностью в формате +375 (XX) XXX-XX-XX';
  }
  return '';
};

const submitCreateLead = async () => {
  if (saving.value) return;
  createPhoneError.value = getPhoneValidationError(createForm.value.phone, createPhoneMask.isComplete.value);
  if (createPhoneError.value) {
    setToast(createPhoneError.value);
    return;
  }
  saving.value = true;
  try {
    const normalizedPhone = createForm.value.phone ? normalizePhoneForApi(createForm.value.phone) : undefined;
    const payload: LeadCreatePayload = {
      ...createForm.value,
      request_text: (createForm.value.request_text || '').trim(),
      name: createForm.value.name || undefined,
      phone: normalizedPhone || undefined,
      email: createForm.value.email || undefined,
      inn: createForm.value.inn || undefined,
      company_name: createForm.value.company_name || undefined,
      next_followup_date: fromLocalDateTimeInput(createForm.value.next_followup_date || undefined) || undefined,
    };
    await api.createManagerLead(payload);
    showCreateModal.value = false;
    resetCreateForm();
    setToast('Лид создан');
    await loadLeads();
  } catch (error) {
    console.error(error);
    setToast(`Не удалось создать лид: ${getErrorMessage(error)}`);
  } finally {
    saving.value = false;
  }
};

const updateLead = async (leadId: number, payload: LeadUpdatePayload, successToast?: string) => {
  if (saving.value) return;
  saving.value = true;
  try {
    await api.patchManagerLead(leadId, payload);
    if (successToast) setToast(successToast);
    await loadLeads();
  } catch (error) {
    console.error(error);
    setToast(`Не удалось обновить лид: ${getErrorMessage(error)}`);
  } finally {
    saving.value = false;
  }
};

const markLost = async (lead: LeadResponse, status: 'lost' | 'spam') => {
  if (saving.value) return;
  saving.value = true;
  try {
    const payload: LeadLossPayload = {
      status,
      loss_reason: status === 'spam' ? 'spam' : 'other',
    };
    await api.markManagerLeadLost(lead.id, payload);
    setToast(status === 'spam' ? 'Лид отмечен как спам' : 'Лид переведен в отказы');
    await loadLeads();
  } catch (error) {
    console.error(error);
    setToast(`Не удалось обновить статус: ${getErrorMessage(error)}`);
  } finally {
    saving.value = false;
  }
};

const openQualifyModal = (lead: LeadResponse) => {
  selectedLead.value = lead;
  qualifyForm.value = {
    name: lead.name || '',
    phone: lead.phone ? normalizePhoneForApi(lead.phone) : '',
    email: lead.email || '',
    inn: lead.inn || '',
    full_legal_name: lead.company_name || '',
    delivery_address: '',
    order_comment: lead.request_text,
  };
  qualifyPhoneError.value = '';
  showQualifyModal.value = true;
};

const qualifyLead = async () => {
  if (!selectedLead.value || saving.value) return;
  qualifyPhoneError.value = getPhoneValidationError(qualifyForm.value.phone, qualifyPhoneMask.isComplete.value);
  if (qualifyPhoneError.value) {
    setToast(qualifyPhoneError.value);
    return;
  }
  saving.value = true;
  try {
    const normalizedPhone = qualifyForm.value.phone ? normalizePhoneForApi(qualifyForm.value.phone) : undefined;
    const response = await api.qualifyManagerLead(selectedLead.value.id, {
      ...qualifyForm.value,
      name: qualifyForm.value.name || undefined,
      phone: normalizedPhone || undefined,
      email: qualifyForm.value.email || undefined,
      inn: qualifyForm.value.inn || undefined,
      full_legal_name: qualifyForm.value.full_legal_name || undefined,
      delivery_address: qualifyForm.value.delivery_address || undefined,
      order_comment: qualifyForm.value.order_comment || undefined,
    });
    showQualifyModal.value = false;
    setToast(`Лид квалифицирован. Сделка #${response.order_id}`);
    await loadLeads();
  } catch (error) {
    console.error(error);
    setToast(`Не удалось квалифицировать лид: ${getErrorMessage(error)}`);
  } finally {
    saving.value = false;
  }
};

const navigateToOrders = (orderId?: number | null) => {
  const path = '/manager/orders/kanban';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
  if (orderId) setToast(`Открыт раздел сделок. Найдите сделку #${orderId}`);
};

let searchTimer: number | undefined;
watch([statusTab, source, overdueOnly, includeArchived, sort], async () => {
  await loadLeads();
});
watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(async () => {
    await loadLeads();
  }, 300);
});

onMounted(async () => {
  await loadLeads();
});

const validateCreatePhoneOnBlur = () => {
  createPhoneError.value = getPhoneValidationError(createForm.value.phone, createPhoneMask.isComplete.value);
};

const validateQualifyPhoneOnBlur = () => {
  qualifyPhoneError.value = getPhoneValidationError(qualifyForm.value.phone, qualifyPhoneMask.isComplete.value);
};
</script>

<template>
  <div class="min-h-screen bg-[var(--mv-bg)] text-slate-100">
    <div class="mx-auto max-w-[1400px] px-4 py-6 md:px-8">
      <header class="mb-5 rounded-[2rem] border border-slate-700/70 bg-gradient-to-r from-slate-900 to-slate-800 p-5">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h1 class="text-2xl font-bold">Leads Dashboard</h1>
          <button class="btn-mini" @click="showCreateModal = true">Новый лид</button>
        </div>

        <div class="mb-3 flex flex-wrap gap-2">
          <button
            v-for="item in tabItems"
            :key="item.key"
            class="rounded-[12px] px-3 py-1.5 text-sm font-semibold transition"
            :class="statusTab === item.key ? 'bg-[var(--mv-teal)] text-white' : 'bg-slate-800 text-slate-300 hover:text-white'"
            @click="statusTab = item.key as LeadTab"
          >
            {{ item.label }}
          </button>
        </div>

        <div class="grid gap-3 md:grid-cols-5">
          <input v-model="search" class="field-input" placeholder="Поиск: имя, телефон, email, УНП, ID" />
          <select v-model="source" class="field-input">
            <option value="">Все источники</option>
            <option value="phone">Телефон</option>
            <option value="site">Сайт</option>
            <option value="bot">Бот</option>
            <option value="email">Email</option>
            <option value="manager">Менеджер</option>
            <option value="other">Другое</option>
          </select>
          <select v-model="sort" class="field-input">
            <option value="created_at_desc">Новые сверху</option>
            <option value="created_at_asc">Старые сверху</option>
            <option value="updated_at_desc">Недавно обновленные</option>
            <option value="followup_asc">Ближайшее касание</option>
          </select>
          <label class="inline-flex items-center gap-2 rounded-[12px] border border-slate-700 bg-slate-900 px-3 py-2">
            <input v-model="overdueOnly" type="checkbox" />
            Только просроченные
          </label>
          <label class="inline-flex items-center gap-2 rounded-[12px] border border-slate-700 bg-slate-900 px-3 py-2">
            <input v-model="includeArchived" type="checkbox" />
            Показать архив
          </label>
        </div>
      </header>

      <p v-if="toast" class="mb-4 rounded-[12px] bg-[#007f80] px-4 py-2 text-sm font-semibold text-white">{{ toast }}</p>
      <p v-if="loading" class="mb-4 text-sm text-slate-300">Загрузка лидов...</p>

      <div v-if="!loading && leads.length === 0" class="rounded-[2rem] border border-slate-700 bg-slate-900/60 p-8 text-center">
        <p class="text-lg font-semibold text-white">Лиды не найдены</p>
        <p class="mt-2 text-sm text-slate-400">Попробуйте изменить фильтры или создайте новый лид.</p>
      </div>

      <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="lead in leads"
          :key="lead.id"
          class="rounded-[2rem] border border-slate-700 bg-slate-800 p-5 shadow-lg"
          :class="isOverdue(lead) ? 'ring-2 ring-red-500/70' : 'ring-1 ring-transparent'"
        >
          <header class="mb-3 flex items-start justify-between gap-2">
            <div>
              <p class="text-lg font-semibold text-white">{{ lead.name || lead.company_name || `Лид #${lead.id}` }}</p>
              <p class="text-sm text-slate-300">{{ lead.phone || lead.email || 'Контакт не указан' }}</p>
            </div>
            <span class="rounded-full bg-slate-700 px-2 py-1 text-xs text-slate-200">{{ statusLabels[lead.status] || lead.status }}</span>
          </header>

          <div class="space-y-1 text-sm text-slate-200">
            <p>Источник: <span class="text-slate-300">{{ sourceLabels[lead.source] || lead.source }}</span></p>
            <p>Сегмент: <span class="text-slate-300">{{ segmentLabels[lead.segment_hint] || lead.segment_hint }}</span></p>
            <p v-if="lead.inn">УНП: {{ lead.inn }}</p>
            <p class="line-clamp-3">{{ lead.request_text }}</p>
            <p class="text-xs text-slate-400">След. касание: {{ formatDate(lead.next_followup_date) }}</p>
            <p v-if="lead.loss_reason" class="text-xs text-amber-300">Причина: {{ lead.loss_reason }}</p>
            <p v-if="lead.converted_order_id" class="text-xs text-emerald-300">Сделка: #{{ lead.converted_order_id }}</p>
          </div>

          <footer class="mt-4 flex flex-wrap gap-2">
            <button
              v-if="lead.status === 'new'"
              class="btn-mini-outline"
              :disabled="saving"
              @click="updateLead(lead.id, { status: 'contacted' }, 'Лид отмечен как обработанный')"
            >
              Связаться
            </button>
            <button
              v-if="lead.status === 'new' || lead.status === 'contacted'"
              class="btn-mini"
              :disabled="saving"
              @click="openQualifyModal(lead)"
            >
              Квалифицировать
            </button>
            <button
              v-if="lead.status === 'new' || lead.status === 'contacted'"
              class="btn-mini-outline"
              :disabled="saving"
              @click="markLost(lead, 'lost')"
            >
              Отказ
            </button>
            <button
              v-if="lead.status === 'new' || lead.status === 'contacted'"
              class="btn-mini-outline"
              :disabled="saving"
              @click="markLost(lead, 'spam')"
            >
              Спам
            </button>
            <button
              v-if="lead.converted_order_id"
              class="btn-mini-outline"
              @click="navigateToOrders(lead.converted_order_id)"
            >
              К сделке
            </button>
          </footer>
        </article>
      </div>
    </div>

    <div v-if="showCreateModal" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div class="w-full max-w-2xl rounded-[2rem] border border-slate-700 bg-slate-900 p-6">
        <h2 class="mb-4 text-xl font-semibold">Новый лид</h2>
        <div class="grid gap-3 md:grid-cols-2">
          <input v-model="createForm.name" class="field-input" placeholder="Имя / Компания" />
          <label class="field-label">
            <span>Телефон</span>
            <input
              ref="createPhoneInputRef"
              v-model="createForm.phone"
              class="field-input"
              :class="createPhoneError ? 'border-red-500 focus:outline-red-400' : ''"
              type="tel"
              inputmode="tel"
              placeholder="+375 (XX) XXX-XX-XX"
              @blur="validateCreatePhoneOnBlur"
            />
            <span v-if="createPhoneError" class="text-xs text-red-300">{{ createPhoneError }}</span>
          </label>
          <input v-model="createForm.email" class="field-input" placeholder="Email" />
          <input v-model="createForm.inn" class="field-input" placeholder="УНП" />
          <input v-model="createForm.company_name" class="field-input" placeholder="Полное название компании" />
          <select v-model="createForm.source" class="field-input">
            <option value="manager">Менеджер</option>
            <option value="phone">Телефон</option>
            <option value="site">Сайт</option>
            <option value="bot">Бот</option>
            <option value="email">Email</option>
            <option value="other">Другое</option>
          </select>
          <DateTimeField
            v-model="createForm.next_followup_date"
            class="md:col-span-2"
            label="Следующее касание"
            placeholder="дд.мм.гггг, --:--"
          />
          <label class="field-label md:col-span-2">
            <span>Запрос</span>
            <textarea
              v-model="createForm.request_text"
              class="field-input min-h-[100px]"
              placeholder="Краткое описание запроса"
            />
          </label>
        </div>
        <div class="mt-5 flex justify-end gap-2">
          <button class="btn-mini-outline" :disabled="saving" @click="showCreateModal = false">Отмена</button>
          <button class="btn-mini" :disabled="saving" @click="submitCreateLead">Создать</button>
        </div>
      </div>
    </div>

    <div v-if="showQualifyModal && selectedLead" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div class="w-full max-w-2xl rounded-[2rem] border border-slate-700 bg-slate-900 p-6">
        <h2 class="mb-4 text-xl font-semibold">Квалифицировать лид #{{ selectedLead.id }}</h2>
        <div class="grid gap-3 md:grid-cols-2">
          <input v-model="qualifyForm.name" class="field-input" placeholder="Имя клиента" />
          <label class="field-label">
            <span>Телефон</span>
            <input
              ref="qualifyPhoneInputRef"
              v-model="qualifyForm.phone"
              class="field-input"
              :class="qualifyPhoneError ? 'border-red-500 focus:outline-red-400' : ''"
              type="tel"
              inputmode="tel"
              placeholder="+375 (XX) XXX-XX-XX"
              @blur="validateQualifyPhoneOnBlur"
            />
            <span v-if="qualifyPhoneError" class="text-xs text-red-300">{{ qualifyPhoneError }}</span>
          </label>
          <input v-model="qualifyForm.email" class="field-input" placeholder="Email" />
          <input v-model="qualifyForm.inn" class="field-input" placeholder="УНП" />
          <input v-model="qualifyForm.full_legal_name" class="field-input md:col-span-2" placeholder="Полное наименование (для юрлица)" />
          <input v-model="qualifyForm.delivery_address" class="field-input md:col-span-2" placeholder="Адрес доставки/монтажа" />
          <label class="field-label md:col-span-2">
            <span>Комментарий сделки</span>
            <textarea v-model="qualifyForm.order_comment" class="field-input min-h-[90px]" />
          </label>
        </div>
        <div class="mt-5 flex justify-end gap-2">
          <button class="btn-mini-outline" :disabled="saving" @click="showQualifyModal = false">Отмена</button>
          <button class="btn-mini" :disabled="saving" @click="qualifyLead">Создать клиента и сделку</button>
        </div>
      </div>
    </div>
  </div>
</template>
