<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, reactive, ref } from 'vue';
import { ArrowLeft, Archive, Plus } from 'lucide-vue-next';
import { api } from '../api';
import type { ManagerCatalogCustomerItemResponse } from '../client';
import CustomerContactsPanel from '../components/customers/CustomerContactsPanel.vue';
import CustomerDetailsPanel from '../components/customers/CustomerDetailsPanel.vue';
import CustomerIntakeDialog from '../components/customers/CustomerIntakeDialog.vue';
import CreateOrderModal from '../components/CreateOrderModal.vue';
import { customerPartyLabel, normalizeCustomerPartyType } from '../components/customers/customer-profile-form';
import { dispatchCustomerUpdated } from '../utils/customer-events';
import { getApiErrorMessage } from '../utils/api-errors';
import { confirmDialog, notify } from '../services/ui-feedback';
import { registerUnsavedNavigationGuard, runGuardedNavigation } from '../services/unsaved-navigation-guard';

const CustomerContractsPanel = defineAsyncComponent(() => import('../components/customers/CustomerContractsPanel.vue'));
const CustomerDocumentsPanel = defineAsyncComponent(() => import('../components/customers/CustomerDocumentsPanel.vue'));
const CustomerEquipmentPanel = defineAsyncComponent(() => import('../components/customers/CustomerEquipmentPanel.vue'));
const CustomerReconciliationPanel = defineAsyncComponent(() => import('../components/customers/CustomerReconciliationPanel.vue'));
const params = new URLSearchParams(window.location.search);
const customerId = Number(params.get('customerId'));
const initialTab = params.get('openContract') === '1' ? 'documents' : 'contacts';
type Tab = 'contacts' | 'documents' | 'reconciliation' | 'equipment';
const activeTab = ref<Tab>(initialTab);
const visited = reactive(new Set<Tab>([initialTab]));
const customer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const loading = ref(true);
const error = ref('');
const showIntake = ref(false);
const showCreateOrder = ref(false);
const archiving = ref(false);
const contactsDirty = ref(false);
const detailsDirty = ref(false);
const dirty = computed(() => contactsDirty.value || detailsDirty.value);
const tabItems: Array<{ id: Tab; label: string }> = [{ id: 'contacts', label: 'Контакты и реквизиты' }, { id: 'documents', label: 'Документы' }, { id: 'reconciliation', label: 'Взаиморасчёты' }, { id: 'equipment', label: 'Оборудование' }];
let alive = true;
async function load() {
  if (!Number.isSafeInteger(customerId) || customerId < 1) { error.value = 'Не указан клиент'; loading.value = false; return; }
  error.value = '';
  try { const result = await api.getManagerCustomerDetail(customerId); if (alive) customer.value = result; }
  catch(e) { if (alive) error.value = getApiErrorMessage(e); }
  finally { if (alive) loading.value = false; }
}
function updated(value: ManagerCatalogCustomerItemResponse) { customer.value = value; dispatchCustomerUpdated(value); }
async function refreshContacts() { await load(); if (customer.value) dispatchCustomerUpdated(customer.value); }
function chooseTab(tab: Tab) { visited.add(tab); activeTab.value = tab; }
function navigate(path: string) { void runGuardedNavigation(() => { window.history.pushState({}, '', path); window.dispatchEvent(new PopStateEvent('popstate')); }); }
function back() { const target = params.get('returnTo'); navigate(target?.startsWith('/manager/') ? target : '/manager/customers'); }
function openOrders() { navigate(`/manager/orders/kanban?customerId=${customerId}&segment=all`); }
function createdOrder(orderId: number) { showCreateOrder.value = false; navigate(`/manager/orders/kanban?orderId=${orderId}`); }
function recognized(value: ManagerCatalogCustomerItemResponse) { showIntake.value = false; updated(value); contactsRevision.value++; }
const contactsRevision = ref(0);
async function openIntake() {
  if (dirty.value) { notify('Сначала сохраните или отмените изменения в карточке', 'info'); return; }
  showIntake.value = true;
}
async function archive() {
  if (!customer.value || archiving.value) return;
  if (dirty.value) { notify('Сначала сохраните изменения', 'info'); return; }
  archiving.value = true;
  try { const value = await api.patchManagerCustomer(customerId, { is_archived: !customer.value.is_archived }); updated(value); notify(value.is_archived ? 'Клиент в архиве' : 'Клиент возвращён из архива', 'success'); }
  catch(e) { notify(getApiErrorMessage(e), 'error'); }
  finally { archiving.value = false; }
}
const unregisterGuard = registerUnsavedNavigationGuard(async () => !dirty.value || await confirmDialog({ title: 'Покинуть карточку?', description: 'Изменения контактов или реквизитов ещё не сохранены.', confirmText: 'Покинуть' }));
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = ''; } }
onMounted(() => { void load(); window.addEventListener('beforeunload', beforeUnload); });
onUnmounted(() => { alive = false; unregisterGuard(); window.removeEventListener('beforeunload', beforeUnload); });
</script>
<template>
  <div class="customer-workspace">
    <button class="back-link" type="button" @click="back"><ArrowLeft :size="15" />{{ params.get('returnTo') ? 'Назад' : 'Клиенты' }}</button>
    <p v-if="loading" class="workspace-state">Загрузка клиента…</p>
    <div v-else-if="error && !customer" class="workspace-state" role="alert">{{ error }} <button type="button" class="text-brand-600" @click="load">Повторить</button></div>
    <template v-if="customer">
      <p v-if="error" class="workspace-state" role="alert">{{ error }} <button type="button" @click="load">Повторить</button></p>
      <header class="customer-header"><div class="customer-heading"><h1>{{ customer.name || customer.full_legal_name || `Клиент #${customer.id}` }}</h1><div class="customer-meta"><span>{{ customerPartyLabel(normalizeCustomerPartyType(customer.type)) }}</span><span v-if="customer.inn">УНП {{ customer.inn }}</span><button type="button" @click="openOrders">Заказы: {{ customer.order_count }} ↗</button><span v-if="customer.is_archived" class="archive-badge">Архив</span></div></div><div class="customer-tools"><button type="button" class="btn-mini-outline" @click="openIntake">Из реквизитов</button><button type="button" class="btn-mini" @click="showCreateOrder = true"><Plus :size="15" />Заказ</button><button class="archive-action" type="button" :disabled="archiving" :aria-label="customer.is_archived ? 'Вернуть из архива' : 'Архивировать клиента'" :title="customer.is_archived ? 'Вернуть из архива' : 'Архивировать клиента'" @click="archive"><Archive :size="16" /></button></div></header>
      <nav class="customer-tabs" aria-label="Разделы клиента"><button v-for="tab in tabItems" :key="tab.id" type="button" :class="{ active: activeTab === tab.id }" :aria-current="activeTab === tab.id ? 'page' : undefined" @click="chooseTab(tab.id)">{{ tab.label }}</button></nav>
      <div v-if="visited.has('contacts')" v-show="activeTab === 'contacts'" class="contacts-layout"><CustomerContactsPanel :key="`${customer.id}-${contactsRevision}`" :customer="customer" :edit-initially="params.get('editContact') === '1'" @updated="refreshContacts" @dirty="contactsDirty = $event" /><CustomerDetailsPanel :customer="customer" @updated="updated" @dirty="detailsDirty = $event" /></div>
      <div v-if="visited.has('documents')" v-show="activeTab === 'documents'" class="space-y-5"><CustomerContractsPanel v-if="customer.type !== 'individual'" :customer-id="customer.id" /><CustomerDocumentsPanel :customer-id="customer.id" /></div>
      <CustomerReconciliationPanel v-if="visited.has('reconciliation')" v-show="activeTab === 'reconciliation'" :customer-id="customer.id" />
      <CustomerEquipmentPanel v-if="visited.has('equipment')" v-show="activeTab === 'equipment'" :customer="customer" />
      <CustomerIntakeDialog v-if="showIntake" :customer="customer" @close="showIntake = false" @created="recognized" @open-existing="navigate(`/manager/customers/profile?customerId=${$event}`)" />
      <CreateOrderModal v-if="showCreateOrder" :customer-id="customer.id" :customer-name="customer.full_legal_name || customer.name || ''" @close="showCreateOrder = false" @created="createdOrder" />
    </template>
  </div>
</template>
<style scoped>
.customer-workspace { padding: 20px 28px; max-width: 1500px; margin: auto; color: var(--mv-text); }.back-link { display: inline-flex; align-items: center; gap: 5px; color: var(--mv-text-muted); font-size: 12px; margin-bottom: 12px; }.customer-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.customer-heading { min-width: 0; }.customer-heading h1 { font-size: 24px; font-weight: 700; line-height: 1.3; overflow-wrap: anywhere; }.customer-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 12px; margin-top: 5px; font-size: 12px; color: var(--mv-text-muted); }.customer-meta button { color: var(--kitlane-accent-text); }.customer-tools { display: flex; gap: 7px; align-items: center; flex-shrink: 0; }.customer-tools .btn-mini { display: inline-flex; gap: 4px; align-items: center; }.archive-action { padding: 7px; border-radius: 7px; color: var(--mv-text-muted); }.archive-action:hover { background: var(--mv-panel); }.archive-badge { background: var(--mv-panel); padding: 1px 6px; border-radius: 4px; }.customer-tabs { display: flex; gap: 22px; overflow-x: auto; border-bottom: 1px solid var(--mv-border); margin: 18px 0; }.customer-tabs button { flex-shrink: 0; padding: 9px 0; font-size: 13px; border-bottom: 2px solid transparent; color: var(--mv-text-muted); }.customer-tabs button.active { color: var(--kitlane-accent-text); border-color: var(--kitlane-accent-text); font-weight: 600; }.contacts-layout { display: grid; grid-template-columns: 1.15fr 1fr; gap: 18px; align-items: start; }.workspace-state { padding: 30px; border: 1px solid var(--mv-border); border-radius: 10px; background: var(--mv-surface); }
@media(max-width:850px) { .contacts-layout { grid-template-columns: 1fr; } }
@media(max-width:600px) { .customer-workspace { padding: 12px; }.customer-header { flex-wrap: wrap; gap: 10px; }.customer-heading h1 { font-size: 20px; }.back-link { margin-bottom: 8px; }.customer-tools { width: 100%; justify-content: flex-end; }.customer-tools button { font-size: 12px; }.customer-tabs { margin: 12px 0; gap: 18px; }.customer-tabs button { font-size: 12px; }.contacts-layout { gap: 12px; } }
</style>
