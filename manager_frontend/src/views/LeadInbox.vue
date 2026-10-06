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
import QuickIncomingCapture from '../components/leads/QuickIncomingCapture.vue';
import { sourceEquipmentPrefillMessage, type SourceAppliedEvent } from '../services/order-source-review';
import EmailLeadImportPanel from '../components/leads/EmailLeadImportPanel.vue';

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

const showIncomingCapture = ref(false);
const editingIncomingId = ref<number | null>(null);

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
  const deepLinkedId = Number(new URLSearchParams(window.location.search).get('incomingId'));
  if (Number.isSafeInteger(deepLinkedId) && deepLinkedId > 0) {
    editingIncomingId.value = deepLinkedId;
    showIncomingCapture.value = true;
  }
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
  if (inboxSearchTimeout) clearTimeout(inboxSearchTimeout);
});

const clearIncomingDeepLink = () => {
  const url = new URL(window.location.href);
  url.searchParams.delete('incomingId');
  window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
};
const closeIncomingCapture = () => {
  showIncomingCapture.value = false;
  editingIncomingId.value = null;
  clearIncomingDeepLink();
};
const openCreateModal = () => {
  editingIncomingId.value = null;
  clearIncomingDeepLink();
  showIncomingCapture.value = true;
};
const openIncomingEdit = (item: InboxItem) => {
  editingIncomingId.value = item.id;
  const url = new URL(window.location.href);
  url.searchParams.set('incomingId', String(item.id));
  window.history.pushState({}, '', `${url.pathname}${url.search}${url.hash}`);
  showIncomingCapture.value = true;
};
const isQuickIncoming = (item: InboxItem) => Boolean(
  item.entity_kind === 'lead'
  && (item as InboxItem & { intake_state?: string | null }).intake_state,
);
const incomingSaved = async (incoming: { lead_id: number }) => {
  const wasEditing = Boolean(editingIncomingId.value);
  closeIncomingCapture();
  notifyInboxChanged();
  setToast(wasEditing ? `Входящее #${incoming.lead_id} исправлено` : `Входящее #${incoming.lead_id} сохранено`);
  await load();
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
        :quick-incoming="scope !== 'archive' && !item.linked_order_id && isQuickIncoming(item)"
        @qualify="qualifyTarget = $event"
        @review-source="sourceReviewTarget = $event"
        @link-changed="notifyInboxChanged(); load()"
        @updated="updateItem"
        @details-closed="unreadOnly && load()"
        @archived="archived"
        @restore="restoreItem"
        @no-answer="markNoAnswer($event)"
        @edit-incoming="openIncomingEdit(item)"
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

    <!-- ── Quick incoming capture ──────────────────────── -->
    <div
      v-if="showIncomingCapture"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click.self="closeIncomingCapture"
    >
      <QuickIncomingCapture
        :key="editingIncomingId || 'new'"
        :lead-id="editingIncomingId"
        @close="closeIncomingCapture"
        @saved="incomingSaved"
      />

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
