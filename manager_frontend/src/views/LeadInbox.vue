<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { api } from '../api';
import { inboxSourceOptions, leadInboxApi, notifyInboxChanged, type InboxItem, type InboxContactRequest, type InboxScope, type InboxSource } from '../services/lead-inbox';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection, managerStorefrontStorageKey } from '../services/manager-storefront-selection';
import LeadInboxCard from '../components/leads/LeadInboxCard.vue';
import LeadInboxToolbar from '../components/leads/LeadInboxToolbar.vue';
import LeadQualifyModal from '../components/leads/LeadQualifyModal.vue';
import LeadSourceReviewModal from '../components/leads/LeadSourceReviewModal.vue';
import { sourceEquipmentPrefillMessage, type SourceAppliedEvent } from '../services/order-source-review';
import EmailLeadImportPanel from '../components/leads/EmailLeadImportPanel.vue';
import AddressSuggestInput from '../components/ui/AddressSuggestInput.vue';
import { useBelarusPhoneMask } from '../composables/useBelarusPhoneMask';
import { useB2BLookup } from '../composables/useB2BLookup';

const pageLimit = 50;

const scope = ref<InboxScope>('active');
const unreadOnly = ref(false);
const sort = ref<'newest' | 'deadline'>('deadline');
const showEmailImport = ref(false);
const pendingCount = ref(0);
const unreadCount = ref(0);
const sourceCounts = ref<Record<string, number>>({});
const undoTarget = ref<InboxItem | null>(null);
const restoreSaving = ref(false);
const contactSaving = ref(false);
const source = ref<InboxSource>('');
const page = ref(1);
const items = ref<InboxItem[]>([]);
const total = ref(0);
const loading = ref(false);
const loadError = ref('');
const toast = ref('');
const search = ref('');
const appliedSearch = ref('');
let inboxSearchTimeout: ReturnType<typeof setTimeout> | null = null;
let loadRequestId = 0;
let summaryRequestId = 0;
let disposed = false;
let ready = false;

const contextStorageKey = () => {
  const auth = managerSession.auth.value;
  const storefront = managerStorefrontSelection.selectedSlug.value;
  return auth && storefront ? `${managerStorefrontStorageKey(auth)}:${storefront}:lead-inbox` : null;
};
const saveContext = () => {
  const key = contextStorageKey();
  if (!key) return;
  try { window.sessionStorage.setItem(key, JSON.stringify({ scope: scope.value, source: source.value, search: appliedSearch.value, page: page.value, unreadOnly: unreadOnly.value, sort: sort.value })); }
  catch { /* Browsing still works when storage is unavailable. */ }
};
const restoreContext = () => {
  const key = contextStorageKey();
  if (!key) return;
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(key) || '{}');
    if (saved.scope === 'active' || saved.scope === 'archive') scope.value = saved.scope;
    if (inboxSourceOptions.some(option => option.value === saved.source)) source.value = saved.source;
    if (typeof saved.search === 'string') search.value = appliedSearch.value = saved.search.slice(0, 200);
    if (typeof saved.unreadOnly === 'boolean') unreadOnly.value = saved.unreadOnly;
    if (saved.sort === 'newest' || saved.sort === 'deadline') sort.value = saved.sort;
    if (Number.isSafeInteger(saved.page) && saved.page > 0) page.value = saved.page;
  } catch { /* Ignore malformed or inaccessible storage. */ }
};

// Qualify / Reject modals
const qualifyTarget = ref<InboxItem | null>(null);
const sourceReviewTarget = ref<InboxItem | null>(null);

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
let customerSearchRequestId = 0;

const searchCustomer = async () => {
  const requestId = ++customerSearchRequestId;
  if (existingCustomerId.value) return; 

  const query = phoneModelRef.value.replace(/\D/g, '').length >= 3 ? phoneModelRef.value : createForm.value.name;
  
  if (!query || query.length < 3) {
    foundCustomers.value = [];
    return;
  }

  try {
    const res = await api.getManagerCustomers(1, 4, query);
    if (requestId !== customerSearchRequestId) return;
    foundCustomers.value = res.items || [];
  } catch (e) {
    if (requestId !== customerSearchRequestId) return;
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
  customerSearchRequestId += 1;
  existingCustomerId.value = c.id;
  createForm.value.name = c.name || c.full_legal_name || '';
  phoneModelRef.value = c.phone || c.inn || '';
  foundCustomers.value = [];
};

const clearSelectedCustomer = () => {
  customerSearchRequestId += 1;
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
  undoTarget.value = null;
  toast.value = msg;
  setTimeout(() => { if (toast.value === msg) { toast.value = ''; undoTarget.value = null; } }, 8000);
};

const load = async () => {
  const requestId = ++loadRequestId;
  summaryRequestId += 1;
  loading.value = true;
  loadError.value = '';
  saveContext();
  try {
    const result = await api.getLeadsInbox(scope.value, page.value, pageLimit, appliedSearch.value || undefined, source.value || undefined, unreadOnly.value, sort.value);
    if (disposed || requestId !== loadRequestId) return;
    const nextTotal = result.meta?.total ?? result.total;
    if (page.value > 1 && page.value > Math.max(1, result.meta?.pages ?? Math.ceil(nextTotal / pageLimit))) {
      page.value = Math.max(1, result.meta?.pages ?? Math.ceil(nextTotal / pageLimit));
      return;
    }
    items.value = result.items;
    pendingCount.value = result.pending_count ?? (scope.value === 'active' ? nextTotal : pendingCount.value);
    unreadCount.value = result.unread_count ?? result.items.filter(item => item.is_read === false).length;
    sourceCounts.value = result.source_counts ?? {};
    total.value = nextTotal;
  } catch (e) {
    if (disposed || requestId !== loadRequestId) return;
    console.error(e);
    loadError.value = 'Не удалось загрузить входящие. Проверьте соединение и повторите попытку.';
  } finally {
    if (requestId === loadRequestId) loading.value = false;
  }
};

onMounted(async () => {
  restoreContext();
  await nextTick();
  ready = true;
  await load();
});
watch([scope, source, unreadOnly, sort], () => {
  if (inboxSearchTimeout) clearTimeout(inboxSearchTimeout);
  appliedSearch.value = search.value.trim().slice(0, 200);
  page.value = 1;
}, { flush: 'sync' });
watch([scope, source, unreadOnly, sort, page, appliedSearch], () => { if (ready) void load(); });
watch(search, (value) => {
  if (!ready) return;
  loadRequestId += 1;
  loading.value = true;
  if (inboxSearchTimeout) clearTimeout(inboxSearchTimeout);
  inboxSearchTimeout = setTimeout(() => {
    const nextSearch = value.trim().slice(0, 200);
    const changed = appliedSearch.value !== nextSearch || page.value !== 1;
    appliedSearch.value = nextSearch;
    page.value = 1;
    if (!changed) void load();
  }, 300);
});
onBeforeUnmount(() => {
  disposed = true;
  ready = false;
  loadRequestId += 1;
  customerSearchRequestId += 1;
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  if (inboxSearchTimeout) clearTimeout(inboxSearchTimeout);
});

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
  showCreateModal.value = true;
};

const submitCreateLead = async () => {
    if (!createForm.value.request_text?.trim()) {
        setToast('Заполните поле «Запрос»');
        return;
    }
    createSaving.value = true;
    try {
        const created = await api.createManagerOrder({
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
        notifyInboxChanged();
        if (created.status === 'new_lead') {
          setToast(`Обращение #${created.id} создано`);
          await load();
        } else {
          setToast(`Обращение #${created.id} уже в переговорах, открываем карточку`);
          window.history.pushState({}, '', `/manager/orders/kanban?orderId=${created.id}`);
          window.dispatchEvent(new PopStateEvent('popstate'));
        }
    } catch (e: any) {
        console.error(e);
        setToast(`Ошибка: ${e?.message ?? 'Не удалось создать обращение'}`);
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
  qualifyTarget.value = null;
  notifyInboxChanged();
  setToast(`Сделка #${orderId} создана, открываем карточку`);
  window.history.pushState({}, '', `/manager/orders/kanban?orderId=${orderId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const handleSourceApplied = async (result: SourceAppliedEvent) => {
  sourceReviewTarget.value = null;
  notifyInboxChanged();
  if (result.customerAction === 'skip') {
    setToast([`Источник для обращения #${result.orderId} обновлён.`, sourceEquipmentPrefillMessage(result.equipmentPrefill)].filter(Boolean).join(' '));
    await load();
    return;
  }
  setToast([`Данные из источника применены, открываем сделку #${result.orderId}.`, sourceEquipmentPrefillMessage(result.equipmentPrefill)].filter(Boolean).join(' '));
  window.history.pushState({}, '', `/manager/orders/kanban?orderId=${result.orderId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const markNoAnswer = async ({ item, note, nextFollowupAt }: InboxContactRequest) => {
  if (contactSaving.value) return;
  contactSaving.value = true;
  try {
    const updated = await leadInboxApi.noAnswer(item.id, nextFollowupAt, item.entity_kind, note);
    updateItem(updated);
    setToast(`Обращение #${item.id}: нет ответа, остаётся в работе`);
  } catch { setToast('Не удалось сохранить попытку контакта'); }
  finally { contactSaving.value = false; }
};
const updateItem = (updated: InboxItem) => {
  const previous = items.value.find(item => item.id === updated.id && (item.entity_kind || 'order') === (updated.entity_kind || 'order'));
  const wasUnread = previous && (previous.is_read === undefined ? previous.is_new : !previous.is_read);
  const isUnread = updated.is_read === undefined ? updated.is_new : !updated.is_read;
  if (unreadOnly.value && previous && wasUnread !== isUnread) {
    const channel = inboxSourceOptions.some(option => option.value && option.value === updated.source) ? updated.source! : 'other';
    sourceCounts.value = { ...sourceCounts.value, [channel]: Math.max(0, (sourceCounts.value[channel] ?? 0) + (isUnread ? 1 : -1)) };
  }
  items.value = items.value.map(item => item.id === updated.id && (item.entity_kind || 'order') === (updated.entity_kind || 'order') ? updated : item);
  // Refresh counts without remounting an opened card.
  const requestId = ++summaryRequestId;
  void api.getLeadsCounter().then(counter => {
    if (disposed || requestId !== summaryRequestId) return;
    pendingCount.value = counter.pending_count ?? pendingCount.value;
    unreadCount.value = counter.unread_count ?? counter.count;
  }).catch(() => {});
};
const archived = async (item: InboxItem) => {
  setToast(`Обращение #${item.id} в архиве`);
  undoTarget.value = item;
  await load();
};
const restoreItem = async (item: InboxItem) => {
  if (restoreSaving.value) return;
  restoreSaving.value = true;
  try {
    await leadInboxApi.restore(item.id, item.entity_kind);
    undoTarget.value = null;
    notifyInboxChanged();
    setToast(`Обращение #${item.id} возвращено в работу`);
    await load();
  } catch { setToast('Не удалось вернуть обращение в работу'); }
  finally { restoreSaving.value = false; }
};

const onEmailImported = async () => {
  notifyInboxChanged();
  if (scope.value !== 'active') scope.value = 'active';
  else await load();
};
</script>

<template>
  <div class="inbox-workspace">
    <LeadInboxToolbar
      v-model:scope="scope" v-model:source="source" v-model:search="search"
      v-model:unread-only="unreadOnly" v-model:sort="sort"
      :pending-count="pendingCount" :unread-count="unreadCount" :source-counts="sourceCounts"
      :total="total" :loading="loading" :show-email-import="showEmailImport"
      @create="openCreateModal" @toggle-email="showEmailImport = !showEmailImport"
    >
      <template #email-import><EmailLeadImportPanel v-if="showEmailImport" @notice="setToast" @imported="onEmailImported" /></template>
    </LeadInboxToolbar>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-3 text-slate-500 dark:text-slate-400 py-12 justify-center">
      <span class="material-icons-round animate-spin text-brand-500">refresh</span>
      Загрузка...
    </div>

    <div v-else-if="loadError" class="rounded-xl border border-red-200 bg-red-50 p-6 text-center text-red-800 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200" role="alert">
      <p>{{ loadError }}</p>
      <button type="button" class="mt-3 rounded-lg bg-white px-3 py-2 text-sm font-semibold shadow-sm hover:bg-red-100 dark:bg-slate-800 dark:hover:bg-slate-700" @click="load">Повторить</button>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="items.length === 0"
      class="text-center py-16 text-slate-400 dark:text-slate-500"
    >
      <span class="material-icons-round text-5xl mb-3 block opacity-30">inbox</span>
      <p class="text-lg font-medium">
        {{ search || source || unreadOnly ? 'По этому запросу обращений нет' : (scope === 'active' ? 'Входящих нет — всё обработано!' : 'Архив пуст') }}
      </p>
    </div>

    <!-- Feed -->
    <div v-else class="inbox-list">
      <LeadInboxCard
        v-for="item in items"
        :key="`${item.entity_kind || 'order'}:${item.id}`"
        :item="item"
        :is-archive="scope === 'archive'"
        :contact-saving="contactSaving"
        @qualify="qualifyTarget = $event"
        @review-source="sourceReviewTarget = $event"
        @link-changed="notifyInboxChanged(); load()"
        @updated="updateItem"
        @details-closed="unreadOnly && load()"
        @archived="archived"
        @restore="restoreItem"
        @no-answer="markNoAnswer($event)"
      />
    </div>

    <nav v-if="!loading && !loadError && total > pageLimit" class="mt-6 flex items-center justify-center gap-3" aria-label="Страницы входящих">
      <button type="button" class="rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-40 dark:border-slate-700" :disabled="page <= 1" @click="page--">Назад</button>
      <span class="text-sm text-slate-600 dark:text-slate-300">{{ page }} из {{ Math.ceil(total / pageLimit) }}</span>
      <button type="button" class="rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-40 dark:border-slate-700" :disabled="page >= Math.ceil(total / pageLimit)" @click="page++">Далее</button>
    </nav>

    <!-- Toast -->
    <transition name="slide-up">
      <div
        v-if="toast"
        role="status"
        class="fixed bottom-6 left-1/2 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-2xl text-sm font-medium z-50"
      >
        {{ toast }}<button v-if="undoTarget" type="button" class="ml-4 underline text-blue-200" :disabled="restoreSaving" @click="restoreItem(undoTarget)">Отменить</button>
      </div>
    </transition>

    <!-- ── Qualify Modal ──────────────────────────────── -->
    <LeadQualifyModal
      v-if="qualifyTarget"
      :lead="qualifyTarget"
      @close="qualifyTarget = null"
      @success="handleQualifySuccess"
    />
    <LeadSourceReviewModal
      v-if="sourceReviewTarget"
      :open="true"
      :order-id="sourceReviewTarget.id"
      :lead-status="sourceReviewTarget.status"
      @close="sourceReviewTarget = null"
      @applied="handleSourceApplied"
    />

    <!-- ── Create Lead Modal ───────────────────────────── -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="showCreateModal = false"
    >
      <div class="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <span class="material-icons-round text-brand-500">person_add</span>
          Новое обращение
        </h2>

        <div class="space-y-3 relative">
          <!-- Selected Customer Banner -->
          <div v-if="existingCustomerId" class="bg-brand-50 dark:bg-brand-900/30 border border-brand-200 dark:border-brand-800 text-brand-800 dark:text-brand-300 px-3 py-2 rounded-xl flex items-center justify-between text-sm col-span-full">
            <div class="flex items-center gap-2">
              <span class="material-icons-round text-brand-500 text-lg">check_circle</span>
              <span>Привязан клиент: <strong>{{ createForm.name || phoneModelRef || 'Без имени' }}</strong></span>
            </div>
            <button @click="clearSelectedCustomer" class="text-brand-600 hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-200 p-1 rounded-md hover:bg-brand-100 dark:hover:bg-brand-800 transition-colors" title="Отвязать клиента">
              <span class="material-icons-round text-[16px]">close</span>
            </button>
          </div>

          <!-- Client Type Selection -->
          <div class="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit mx-auto col-span-full">
            <button 
              class="px-5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              :class="!createForm.isCompany ? 'bg-white dark:bg-slate-700 shadow-sm text-brand-700 dark:text-brand-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
              @click="createForm.isCompany = false"
            >
              👤 Физ. лицо
            </button>
            <button 
              class="px-5 py-1.5 rounded-lg text-xs font-semibold transition-all"
              :class="createForm.isCompany ? 'bg-white dark:bg-slate-700 shadow-sm text-brand-700 dark:text-brand-400' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'"
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
                class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <div v-if="isEgrLoading" class="absolute right-3 top-7">
                <span class="material-icons-round animate-spin text-brand-500 text-sm">refresh</span>
              </div>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Юр. Название</label>
              <input
                v-model="createForm.fullLegalName"
                type="text"
                placeholder="Полное название"
                class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
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
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div class="relative">
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Телефон</label>
            <input
              ref="createPhoneInputRef"
              v-model="phoneModelRef"
              @input="onSearchInput"
              type="text"
              placeholder="+375 (29) 000-00-00 или +7 916 000-00-00"
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
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
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
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
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
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
                  class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
              <AddressSuggestInput
                v-model="createForm.address"
                label="Адрес объекта"
                placeholder="г. Минск, ул. ..."
                input-class="bg-white text-sm dark:bg-slate-700"
              />
            </div>
          </template>
          <div>
            <label class="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wide">Запрос <span class="text-red-400">*</span></label>
            <textarea
              v-model="createForm.request_text"
              rows="3"
              placeholder="Нужен монтаж кондиционера в квартиру, Минск..."
              class="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>
        </div>

        <div class="flex gap-3 pt-1">
          <button
            class="flex-1 py-2.5 rounded-xl font-semibold text-sm transition-all"
            :class="createSaving ? 'bg-brand-400 text-white cursor-not-allowed' : 'bg-brand-600 text-white hover:bg-brand-700'"
            :disabled="createSaving"
            @click="submitCreateLead"
          >
            {{ createSaving ? 'Сохранение...' : '✅ Создать обращение' }}
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

<style src="./lead-inbox.css"></style>
<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition:  all 0.3s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity:  0;
  transform:  translate(-50%, 12px);
}
</style>
