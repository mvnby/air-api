<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api, type LeadsInboxItemResponse } from '../api';
import { ManagerMailService, ManagerSettingsService, type EmailLeadImportResponse } from '../client';
import LeadInboxCard from '../components/leads/LeadInboxCard.vue';
import LeadQualifyModal from '../components/leads/LeadQualifyModal.vue';
import { useBelarusPhoneMask } from '../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../composables/useB2BLookup';

type Scope = 'active' | 'archive';

const scope = ref<Scope>('active');
const items = ref<LeadsInboxItemResponse[]>([]);
const total = ref(0);
const loading = ref(false);
const toast = ref('');
const emailLeadImporting = ref(false);
const emailLeadImportResult = ref<EmailLeadImportResponse | null>(null);

// Qualify / Reject modals
const qualifyTarget = ref<LeadsInboxItemResponse | null>(null);
const rejectTarget = ref<LeadsInboxItemResponse | null>(null);

// Create Lead modal
const showCreateModal = ref(false);
const createSaving = ref(false);
const createForm = ref({
  source: 'manager',
  request_text: '',
  name: '',
  phone: '',
  service_type: '',
  isCompany: false,
  inn: '',
  fullLegalName: '',
  target_date: '',
  address: '',
});

const { lookupCompany, isEgrLoading } = useB2BLookup();

const createPhoneInputRef = ref<HTMLInputElement | null>(null);
const phoneModelRef = ref('');

const { unmaskedValue: createPhoneUnmasked } = useBelarusPhoneMask(createPhoneInputRef, phoneModelRef);

// Customer Search in Create Modal
const searchTimeout = ref<number | null>(null);
const foundCustomers = ref<any[]>([]);
const existingCustomerId = ref<number | null>(null);

const searchCustomer = async () => {
  if (existingCustomerId.value) return; 

  const query = phoneModelRef.value.replace(/\D/g, '').length >= 3 ? phoneModelRef.value : createForm.value.name;
  
  if (!query || query.length < 3) {
    foundCustomers.value = [];
    return;
  }

  try {
    const res = await api.getManagerCustomers(1, 4, query);
    foundCustomers.value = res.items || [];
  } catch (e) {
    console.error('Customer search failed', e);
    foundCustomers.value = [];
  }
};

const onSearchInput = () => {
  if (existingCustomerId.value) {
     existingCustomerId.value = null;
  }
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  searchTimeout.value = window.setTimeout(searchCustomer, 400);
};

const selectCustomer = (c: any) => {
  existingCustomerId.value = c.id;
  createForm.value.name = c.name || c.full_legal_name || '';
  phoneModelRef.value = c.phone || c.inn || '';
  foundCustomers.value = [];
};

const clearSelectedCustomer = () => {
  existingCustomerId.value = null;
  createForm.value.name = '';
  phoneModelRef.value = '';
  foundCustomers.value = [];
};

watch(phoneModelRef, (val) => {
  createForm.value.phone = val;
});

watch(() => createForm.value.phone, (val) => {
  if (phoneModelRef.value !== val) {
    phoneModelRef.value = val;
  }
});

const setToast = (msg: string) => {
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) toast.value = ''; }, 3000);
};

const getApiErrorMessage = (error: unknown) => {
  if (error instanceof Error && error.message) return error.message;
  return 'неизвестная ошибка';
};

const importEmailLeads = async () => {
  emailLeadImporting.value = true;
  emailLeadImportResult.value = null;
  try {
    const result = await ManagerMailService.importManagerEmailLeads(false);
    emailLeadImportResult.value = result;
    setToast(`Почта: обработано ${result.processed || 0}, кандидатов ${result.candidates || 0}, создано ${result.created || 0}.`);
    if ((result.created || 0) > 0) {
      scope.value = 'active';
      await load();
    }
  } catch (error) {
    setToast(`Не удалось проверить почту: ${getApiErrorMessage(error)}`);
  } finally {
    emailLeadImporting.value = false;
  }
};

const load = async () => {
  loading.value = true;
  try {
    const res = await api.getLeadsInbox(scope.value);
    items.value = res.items;
    total.value = res.total;
  } catch (e) {
    console.error(e);
    setToast('Не удалось загрузить входящие');
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  await load();
});
watch(scope, load);

// ── Address Suggest ─────────────────────────────────────────────────────────
const addressSuggestions = ref<any[]>([]);
const addressSuggestActive = ref(false);
const addressLookupLoading = ref(false);

const fetchAddressSuggestions = async (query: string) => {
  if (!query || query.length < 3) {
    addressSuggestions.value = [];
    return;
  }
  addressLookupLoading.value = true;
  try {
    const res = await ManagerSettingsService.suggestAddress(query);
    addressSuggestions.value = res.results || [];
  } catch (err) {
    console.warn('Failed to fetch address suggestions', err);
  } finally {
    addressLookupLoading.value = false;
  }
};

const debouncedFetchAddressSuggestions = useDebounceFn(fetchAddressSuggestions, 400);

const onAddressInput = () => {
  addressSuggestActive.value = true;
  debouncedFetchAddressSuggestions(createForm.value.address);
};

const selectAddressSuggestion = (item: any) => {
  createForm.value.address = item.title?.text || '';
  if (item.subtitle?.text) createForm.value.address += `, ${item.subtitle.text}`;
  addressSuggestActive.value = false;
  addressSuggestions.value = [];
};

const hideAddressSuggestions = () => {
  setTimeout(() => {
    addressSuggestActive.value = false;
  }, 200);
};

// ── Create Lead ───────────────────────────────────────────────────────────────
const openCreateModal = () => {
  Object.assign(createForm.value, { 
    source: 'manager', 
    request_text: '', 
    name: '', 
    phone: '', 
    service_type: '',
    isCompany: false,
    inn: '',
    fullLegalName: '',
    target_date: '',
    address: '',
  });
  phoneModelRef.value = '';
  existingCustomerId.value = null;
  foundCustomers.value = [];
  addressSuggestions.value = [];
  showCreateModal.value = true;
};

const submitCreateLead = async () => {
    if (!createForm.value.request_text?.trim()) {
        setToast('Заполните поле «Запрос»');
        return;
    }
    createSaving.value = true;
    try {
        await api.createManagerOrder({
            customer_id: existingCustomerId.value || undefined,
            source: createForm.value.source,
            request_text: createForm.value.request_text,
            name: createForm.value.name || undefined,
            phone: createPhoneUnmasked.value || undefined,
            service_type: createForm.value.service_type || undefined,
            customer_type: createForm.value.isCompany ? 'company' : 'individual',
            customer_inn: createForm.value.isCompany ? (createForm.value.inn || undefined) : undefined,
            customer_full_legal_name: createForm.value.isCompany ? (createForm.value.fullLegalName || createForm.value.name || undefined) : undefined,
            address: createForm.value.service_type === 'maintenance' && createForm.value.address ? createForm.value.address : undefined,
            target_date: createForm.value.service_type === 'maintenance' && createForm.value.target_date ? new Date(createForm.value.target_date).toISOString() : undefined,
        });
        showCreateModal.value = false;
        setToast('Лид создан');
        await load();
    } catch (e: any) {
        console.error(e);
        setToast(`Ошибка: ${e?.message ?? 'Не удалось создать лид'}`);
    } finally {
        createSaving.value = false;
    }
};

const onCreateInnBlur = async () => {
    if (!createForm.value.inn || createForm.value.inn.length !== 9) return;
    const data = await lookupCompany(createForm.value.inn);
    if (data) {
        if (!createForm.value.fullLegalName) createForm.value.fullLegalName = data.fullLegalName || '';
        if (!createForm.value.name) createForm.value.name = data.fullLegalName || '';
    }
};

// ── Qualify ───────────────────────────────────────────────────────────────────
const handleQualifySuccess = async (orderId: number) => {
  setToast(`Заявка #${orderId} переведена в Замер`);
  qualifyTarget.value = null;
  await load();
};

// ── No Answer (Недозвон) ──────────────────────────────────────────────────────
const markNoAnswer = async (item: LeadsInboxItemResponse) => {
  try {
    const noAnswerPayload = { 
      status: 'new_lead', 
      no_answer_at: new Date().toISOString() 
    };
    await api.patchManagerOrder(item.id, noAnswerPayload);
    setToast(`Заявка #${item.id} переведена в работу (Недозвон)`);
    await load();
  } catch (e) {
    console.error(e);
    setToast('Ошибка при обновлении статуса');
  }
};

// ── Rejection ─────────────────────────────────────────────────────────────────
const rejectReason = ref('');

const confirmReject = async () => {
  if (!rejectTarget.value) return;
  try {
    const newComment = rejectReason.value
      ? (rejectTarget.value.comment ? `${rejectTarget.value.comment}\n[Отказ: ${rejectReason.value}]` : `[Отказ: ${rejectReason.value}]`)
      : rejectTarget.value.comment;

    await api.patchManagerOrder(rejectTarget.value.id, {
      status: 'closed',
      closing_result: 'lost',
      reject_reason: rejectReason.value || undefined,
      comment: newComment || undefined,
    });
    setToast(`Заявка #${rejectTarget.value.id} перемещена в архив`);
    rejectTarget.value = null;
    rejectReason.value = '';
    await load();
  } catch (e) {
    console.error(e);
    setToast('Ошибка при отклонении');
  }
};

const openRejectModal = (item: LeadsInboxItemResponse) => {
  rejectTarget.value = item;
  rejectReason.value = '';
};

const scopeOptions: { value: Scope; label: string }[] = [
  { value: 'active', label: 'Активные' },
  { value: 'archive', label: 'Архив' },
];
</script>

<template>
  <div class="p-6 bg-slate-50 dark:bg-[#0f172a] min-h-full text-slate-900 dark:text-white transition-colors duration-200">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6 gap-4 flex-wrap">
      <h1 class="text-2xl font-bold flex items-center gap-3">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">move_to_inbox</span>
        Входящие
        <span
          v-if="total > 0 && scope === 'active'"
          class="inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-sm font-bold bg-red-500 text-white ml-1"
        >{{ total }}</span>
      </h1>

      <div class="flex items-center gap-2">
        <!-- Create Lead button -->
        <button
          class="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold bg-teal-600 text-white hover:bg-teal-700 active:scale-95 transition-all shadow-sm"
          @click="openCreateModal"
        >
          <span class="material-icons-round text-[18px]">add</span>
          Создать лид
        </button>

        <!-- Scope filter -->
        <div class="flex rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-medium shadow-sm">
          <button
            v-for="opt in scopeOptions"
            :key="opt.value"
            class="px-4 py-2 transition-colors"
            :class="scope === opt.value
              ? 'bg-teal-600 text-white'
              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'"
            @click="scope = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
    </div>

    <section class="mb-6 rounded-2xl border border-teal-200 bg-white p-4 shadow-sm dark:border-teal-500/20 dark:bg-slate-800">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p class="text-sm font-bold uppercase tracking-wide text-teal-700 dark:text-teal-300">Email-лиды</p>
          <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Проверка новых писем с последнего прохода; при первом запуске берутся последние 5 дней.
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            class="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-teal-700 disabled:opacity-60"
            :disabled="emailLeadImporting"
            @click="importEmailLeads"
          >
            <span class="material-icons-round text-[18px]" :class="{ 'animate-spin': emailLeadImporting }">
              {{ emailLeadImporting ? 'refresh' : 'mark_email_read' }}
            </span>
            {{ emailLeadImporting ? 'Проверяем...' : 'Проверить почту' }}
          </button>
        </div>
      </div>
      <div
        v-if="emailLeadImportResult"
        class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600 dark:text-slate-300"
      >
        <span>Обработано: {{ emailLeadImportResult.processed || 0 }}</span>
        <span v-if="emailLeadImportResult.scanned_since">С: {{ new Date(emailLeadImportResult.scanned_since).toLocaleString('ru-RU') }}</span>
        <span>Кандидатов: {{ emailLeadImportResult.candidates || 0 }}</span>
        <span>AI: {{ emailLeadImportResult.ai_checked || 0 }}</span>
        <span>Создано: {{ emailLeadImportResult.created || 0 }}</span>
        <span>Дубли: {{ emailLeadImportResult.duplicates || 0 }}</span>
        <span>Отклонено: {{ emailLeadImportResult.rejected || 0 }}</span>
        <span>Ошибки: {{ emailLeadImportResult.failed || 0 }}</span>
      </div>
      <div
        v-if="emailLeadImportResult?.decisions?.length"
        class="mt-3 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700"
      >
        <div
          v-for="(decision, index) in emailLeadImportResult.decisions"
          :key="`${decision.sender_email}-${decision.subject}-${decision.status}-${index}`"
          class="grid gap-2 border-b border-slate-100 px-3 py-2 text-sm last:border-b-0 dark:border-slate-700 md:grid-cols-[120px_minmax(0,1fr)_minmax(0,2fr)]"
        >
          <span class="font-semibold text-slate-700 dark:text-slate-200">
            {{ decision.status === 'rejected' ? 'Отклонено' : decision.status === 'would_create' ? 'Кандидат' : decision.status === 'created' ? 'Создан' : decision.status === 'duplicate' ? 'Дубль' : 'Ошибка' }}
            <span v-if="decision.order_id" class="text-slate-400">#{{ decision.order_id }}</span>
          </span>
          <span class="min-w-0 truncate text-slate-600 dark:text-slate-300">
            {{ decision.subject || 'Без темы' }}
          </span>
          <span class="min-w-0 text-slate-500 dark:text-slate-400">
            {{ decision.reason || decision.sender_email }}
          </span>
        </div>
      </div>
    </section>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-3 text-slate-500 dark:text-slate-400 py-12 justify-center">
      <span class="material-icons-round animate-spin text-teal-500">refresh</span>
      Загрузка...
    </div>

    <!-- Empty state -->
    <div
      v-else-if="items.length === 0"
      class="text-center py-16 text-slate-400 dark:text-slate-500"
    >
      <span class="material-icons-round text-5xl mb-3 block opacity-30">inbox</span>
      <p class="text-lg font-medium">
        {{ scope === 'active' ? 'Входящих нет — всё обработано!' : 'Архив пуст' }}
      </p>
    </div>

    <!-- Feed -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <LeadInboxCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :is-archive="scope === 'archive'"
        @qualify="qualifyTarget = $event"
        @reject="openRejectModal($event)"
        @no-answer="markNoAnswer($event)"
      />
    </div>

    <!-- Toast -->
    <transition name="slide-up">
      <div
        v-if="toast"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-2xl text-sm font-medium z-50"
      >
        {{ toast }}
      </div>
    </transition>

    <!-- ── Qualify Modal ──────────────────────────────── -->
    <LeadQualifyModal
      v-if="qualifyTarget"
      :lead="qualifyTarget"
      @close="qualifyTarget = null"
      @success="handleQualifySuccess"
    />

    <!-- ── Reject Modal ───────────────────────────────── -->
    <div
      v-if="rejectTarget"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="rejectTarget = null"
    >
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-sm w-full p-6 space-y-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-icons-round text-red-500">cancel</span>
          Отказать по заявке #{{ rejectTarget.id }}
        </h2>
        <p class="text-sm text-slate-600 dark:text-slate-300">
          Заявка будет перемещена в архив со статусом <strong>«Отменена»</strong>.
        </p>

        <div>
          <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Причина отказа (опционально)</label>
          <input
            v-model="rejectReason"
            type="text"
            placeholder="Например: Дорого, Нецелевой, Спам"
            class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500"
          />
        </div>

        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700 transition-colors text-sm"
            @click="confirmReject"
          >⛔ Подтвердить</button>
          <button
            class="flex-1 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors text-sm"
            @click="rejectTarget = null"
          >Отмена</button>
        </div>
      </div>
    </div>

    <!-- ── Create Lead Modal ───────────────────────────── -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="showCreateModal = false"
    >
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-icons-round text-teal-500">person_add</span>
          Новый лид
        </h2>

        <div class="space-y-3 relative">
          <!-- Selected Customer Banner -->
          <div v-if="existingCustomerId" class="bg-teal-50 dark:bg-teal-900/30 border border-teal-200 dark:border-teal-800 text-teal-800 dark:text-teal-300 px-3 py-2 rounded-xl flex items-center justify-between text-sm col-span-full">
            <div class="flex items-center gap-2">
              <span class="material-icons-round text-teal-500 text-lg">check_circle</span>
              <span>Привязан клиент: <strong>{{ createForm.name || phoneModelRef || 'Без имени' }}</strong></span>
            </div>
            <button @click="clearSelectedCustomer" class="text-teal-600 hover:text-teal-800 dark:text-teal-400 dark:hover:text-teal-200 p-1 rounded-md hover:bg-teal-100 dark:hover:bg-teal-800 transition-colors" title="Отвязать клиента">
              <span class="material-icons-round text-[16px]">close</span>
            </button>
          </div>

          <!-- Client Type Selection -->
          <div class="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit mx-auto col-span-full">
            <button 
              class="px-5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              :class="!createForm.isCompany ? 'bg-white dark:bg-slate-700 shadow-sm text-teal-700 dark:text-teal-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
              @click="createForm.isCompany = false"
            >
              👤 Физ. лицо
            </button>
            <button 
              class="px-5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              :class="createForm.isCompany ? 'bg-white dark:bg-slate-700 shadow-sm text-teal-700 dark:text-teal-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
              @click="createForm.isCompany = true"
            >
              🏢 Юр. лицо
            </button>
          </div>

          <div v-if="createForm.isCompany" class="col-span-full grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="relative">
              <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">УНП</label>
              <input
                v-model="createForm.inn"
                @blur="onCreateInnBlur"
                type="text"
                placeholder="9 цифр"
                class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
              <div v-if="isEgrLoading" class="absolute right-3 top-7">
                <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
              </div>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Юр. Название</label>
              <input
                v-model="createForm.fullLegalName"
                type="text"
                placeholder="Полное название"
                class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Имя / Компания</label>
            <input
              v-model="createForm.name"
              @input="onSearchInput"
              type="text"
              placeholder="Иванов Иван / МастерВоздуха"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
          </div>
          <div class="relative">
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Телефон</label>
            <input
              ref="createPhoneInputRef"
              v-model="phoneModelRef"
              @input="onSearchInput"
              type="text"
              placeholder="+375 (29) 000-00-00"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
            />

            <!-- Autocomplete Dropdown -->
            <div v-if="foundCustomers.length > 0 && !existingCustomerId" class="absolute z-10 w-full left-0 top-[100%] bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl shadow-lg mt-1 max-h-48 overflow-y-auto">
              <button
                v-for="c in foundCustomers"
                :key="c.id"
                @click="selectCustomer(c)"
                class="w-full text-left px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-0"
              >
                <div class="text-sm font-semibold text-slate-800 dark:text-white">{{ c.name || c.full_legal_name || 'Без имени' }}</div>
                <div class="text-xs text-slate-500 dark:text-slate-400">{{ c.phone || c.inn || 'Нет данных' }} <span class="text-[10px] ml-1 opacity-50">{{ c.type === 'company' ? 'Юр. лицо' : 'Физ. лицо' }}</span></div>
              </button>
            </div>
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Источник</label>
            <select
              v-model="createForm.source"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="manager">Менеджер (звонок/офис)</option>
              <option value="phone">Входящий звонок</option>
              <option value="site">Сайт</option>
              <option value="other">Другое</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Суть задачи</label>
            <select
              v-model="createForm.service_type"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="">— Не указано —</option>
              <option value="turnkey">📦 Покупка + Монтаж</option>
              <option value="install_only">🔧 Только монтаж</option>
              <option value="pre_install">🧱 Закладка трассы (Ремонт)</option>
              <option value="maintenance">❄️ Сервис / ТО</option>
              <option value="repair">🛠 Ремонт</option>
              <option value="dismantling">🏗️ Демонтаж</option>
            </select>
          </div>
          <template v-if="createForm.service_type === 'maintenance'">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 col-span-full">
              <div>
                <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Дата и время ТО</label>
                <input
                  v-model="createForm.target_date"
                  type="datetime-local"
                  class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>
              <div class="relative">
                <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Адрес объекта</label>
                <div class="relative">
                  <input
                    v-model="createForm.address"
                    @input="onAddressInput"
                    @blur="hideAddressSuggestions"
                    type="text"
                    placeholder="г. Минск, ул. ..."
                    class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                  <div v-if="addressLookupLoading" class="absolute right-3 top-2.5">
                    <span class="material-icons-round animate-spin text-teal-500 text-sm">refresh</span>
                  </div>
                </div>

                <!-- Autocomplete Dropdown for Address -->
                <div v-if="addressSuggestActive && addressSuggestions.length > 0" class="absolute z-10 w-full left-0 top-[100%] bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl shadow-lg mt-1 max-h-48 overflow-y-auto">
                  <button
                    v-for="(sug, sidx) in addressSuggestions"
                    :key="sidx"
                    @click.prevent="selectAddressSuggestion(sug)"
                    class="w-full text-left px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-700 border-b border-slate-100 dark:border-slate-700 last:border-0"
                  >
                    <div class="text-sm font-semibold text-slate-800 dark:text-white">{{ sug.title?.text || sug.value }}</div>
                    <div v-if="sug.subtitle?.text" class="text-xs text-slate-500 dark:text-slate-400">{{ sug.subtitle.text }}</div>
                  </button>
                </div>
              </div>
            </div>
          </template>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Запрос <span class="text-red-400">*</span></label>
            <textarea
              v-model="createForm.request_text"
              rows="3"
              placeholder="Нужен монтаж кондиционера в квартиру, Минск..."
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500 resize-none"
            />
          </div>
        </div>

        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl font-semibold text-sm transition-all"
            :class="createSaving ? 'bg-teal-400 text-white cursor-not-allowed' : 'bg-teal-600 text-white hover:bg-teal-700'"
            :disabled="createSaving"
            @click="submitCreateLead"
          >
            {{ createSaving ? 'Сохранение...' : '✅ Создать лид' }}
          </button>
          <button
            class="flex-1 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold text-sm hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            @click="showCreateModal = false"
          >Отмена</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from,
.slide-up-leave-to { opacity: 0; transform: translate(-50%, 12px); }
</style>
