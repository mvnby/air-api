<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Inbox, Loader2 } from 'lucide-vue-next';
import { api } from '../api';
import { globalIncomingCapturedEvent, inboxSourceOptions, leadInboxApi, notifyInboxChanged, type InboxItem, type InboxContactRequest, type InboxScope, type InboxSource } from '../services/lead-inbox';
import { hasManagerCapability, MANAGER_CAPABILITY } from '../manager-capabilities';
import { navigateManager, openManagerChild, replaceManagerLocation, returnToManager } from '../services/manager-navigation-history';
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

const params = new URLSearchParams(window.location.search);
const requestedKind = params.get('kind');
const requestedId = Number(params.get('itemId'));
const focusItem = (requestedKind === 'lead' || requestedKind === 'order') && Number.isSafeInteger(requestedId) && requestedId > 0
  ? { id: requestedId, kind: requestedKind } as const : null;
const originTask = Number(params.get('taskId'));
const marketParent = window.history.state?.managerReturn?.href;
const marketPath = typeof marketParent === 'string' && marketParent.split('?')[0] === '/manager/tenders' ? marketParent : '/manager/tenders';
const canMonitor = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.tenderMarket));
let restoreScroll = 0;
const toMonitor = () => { rememberPosition(); void openManagerChild('/manager/tenders?from=inbox'); };
const reloadGlobalCapture = () => { void load(); };
const contextStorageKey = () => {
  const auth = managerSession.auth.value;
  const storefront = managerStorefrontSelection.selectedSlug.value;
  return auth && storefront ? `${managerStorefrontStorageKey(auth)}:${storefront}:lead-inbox` : null;
};
const rememberPosition = () => {
  const key = contextStorageKey();
  if (!key || focusItem) return;
  try { window.sessionStorage.setItem(key + ':top', String(window.scrollY)); } catch { /* Optional list position. */ }
};
const saveContext = () => {
  if (focusItem) return;
  const key = contextStorageKey();
  if (!key) return;
  try { window.sessionStorage.setItem(key, JSON.stringify({ scope: scope.value, source: source.value, search: appliedSearch.value, page: page.value, unreadOnly: unreadOnly.value, sort: sort.value })); }
  catch { /* Browsing still works when storage is unavailable. */ }
};
const restoreContext = () => {
  const key = contextStorageKey();
  if (!key) return;
  try {
    restoreScroll = Math.max(0, Number(window.sessionStorage.getItem(key + ':top')) || 0);
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
    if (focusItem) {
      const item = await leadInboxApi.detail(focusItem.id, focusItem.kind);
      if (disposed || requestId !== loadRequestId) return;
      items.value = [item];
      total.value = 1;
      return;
    }
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
    loadError.value = focusItem ? 'Обращение недоступно в выбранной компании и витрине.' : 'Не удалось загрузить входящие. Проверьте соединение и повторите попытку.';
  } finally {
    if (requestId === loadRequestId) loading.value = false;
  }
};

onMounted(async () => {
  window.addEventListener(globalIncomingCapturedEvent, reloadGlobalCapture);
  restoreContext();
  if (params.get('source') === 'belzakupki' && source.value !== 'belzakupki') {
    source.value = 'belzakupki'; scope.value = 'active'; unreadOnly.value = false; search.value = appliedSearch.value = ''; page.value = 1; restoreScroll = 0;
  }
  const deepLinkedId = Number(new URLSearchParams(window.location.search).get('incomingId'));
  if (Number.isSafeInteger(deepLinkedId) && deepLinkedId > 0) {
    editingIncomingId.value = deepLinkedId;
    showIncomingCapture.value = true;
  }
  await nextTick();
  ready = true;
  await load();
  if (!disposed && !focusItem && restoreScroll > 0) { await nextTick(); window.scrollTo(0, restoreScroll); }
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
  rememberPosition();
  window.removeEventListener(globalIncomingCapturedEvent, reloadGlobalCapture);
  disposed = true;
  ready = false;
  loadRequestId += 1;
  if (inboxSearchTimeout) clearTimeout(inboxSearchTimeout);
});

const clearIncomingDeepLink = () => {
  const url = new URL(window.location.href);
  url.searchParams.delete('incomingId');
  replaceManagerLocation(url.pathname + url.search);
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
  replaceManagerLocation(url.pathname + url.search);
  showIncomingCapture.value = true;
};
const isQuickIncoming = (item: InboxItem) => Boolean(
  item.entity_kind === 'lead'
  && (item as InboxItem & { intake_state?: string | null }).intake_state,
);
const incomingCaptured = async (incoming: { lead_id: number }) => {
  notifyInboxChanged();
  setToast(`Входящее #${incoming.lead_id} сохранено`);
  await load();
};
const incomingSaved = async (incoming: { lead_id: number }) => {
  const wasEditing = Boolean(editingIncomingId.value);
  closeIncomingCapture();
  notifyInboxChanged();
  setToast(wasEditing ? `Входящее #${incoming.lead_id} исправлено` : `Входящее #${incoming.lead_id} сохранено`);
  await load();
};

// ── Qualify ───────────────────────────────────────────────────────────────────
const openQualification = (item: InboxItem) => {
  if (item.entity_kind !== 'lead' && item.source === 'belzakupki' && !item.linked_order_id) {
    sourceReviewTarget.value = item;
  } else {
    qualifyTarget.value = item;
  }
};

const handleQualifySuccess = async (orderId: number) => {
  qualifyTarget.value = null;
  notifyInboxChanged();
  setToast(`Сделка #${orderId} создана, открываем карточку`);
  void openManagerChild(`/manager/orders/${orderId}?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`);
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
  void openManagerChild(`/manager/orders/${result.orderId}?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`);
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
    <header v-if="focusItem" class="mb-4 flex flex-wrap items-center gap-3">
      <h1 class="text-xl font-bold">Входящее №{{ focusItem.id }}</h1>
      <a v-if="canMonitor && params.get('from') === 'market'" :href="marketPath" class="text-sm font-semibold text-brand-700 underline" @click.exact.prevent="returnToManager(marketPath)">К мониторингу</a>
      <a v-if="Number.isSafeInteger(originTask) && originTask > 0" :href="`/manager/tasks?taskId=${originTask}`" class="text-sm font-semibold text-brand-700 underline" @click.exact.prevent="returnToManager(`/manager/tasks?taskId=${originTask}`)">К поручению</a>
      <a href="/manager/leads" class="text-sm font-semibold text-brand-700 underline" @click.exact.prevent="navigateManager('/manager/leads')">К списку входящих</a>
    </header>
    <LeadInboxToolbar v-else
      :show-tender-source="canMonitor"
      v-model:scope="scope" v-model:source="source" v-model:search="search"
      v-model:unread-only="unreadOnly" v-model:sort="sort"
      :pending-count="pendingCount" :unread-count="unreadCount" :source-counts="sourceCounts"
      :total="total" :loading="loading" :show-email-import="showEmailImport"
      @create="openCreateModal" @toggle-email="showEmailImport = !showEmailImport"
    >
      <template #email-import><EmailLeadImportPanel v-if="showEmailImport" @notice="setToast" @imported="onEmailImported" /></template>
    </LeadInboxToolbar>

    <a v-if="canMonitor && params.get('from') !== 'market' && (focusItem ? items[0]?.source === 'belzakupki' : source === 'belzakupki')" href="/manager/tenders?from=inbox" class="mb-3 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-brand-700 underline dark:text-brand-300" @click.exact.prevent="toMonitor">Мониторинг тендеров <span aria-hidden="true">→</span></a>
    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-3 text-slate-500 dark:text-slate-400 py-12 justify-center">
      <Loader2 class="animate-spin text-brand-500" :size="22" aria-hidden="true" />
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
      <Inbox class="mx-auto mb-3 opacity-30" :size="42" aria-hidden="true" />
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
        :is-archive="focusItem ? Boolean(item.archive || item.linked_order_id) : scope === 'archive'"
        :contact-saving="contactSaving"
        :quick-incoming="(focusItem ? !item.archive : scope !== 'archive') && !item.linked_order_id && isQuickIncoming(item)"
        @qualify="openQualification"
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
        @captured="incomingCaptured"
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
