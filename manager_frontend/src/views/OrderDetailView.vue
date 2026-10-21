<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue';
import { ArrowLeft, Loader2 } from 'lucide-vue-next';
import { api } from '../api';
import type { OrderWithResponsibility } from '../services/order-responsibility';
import OrderEditDrawer from '../components/orders/OrderEditDrawer.vue';
import { registerUnsavedNavigationGuard } from '../services/unsaved-navigation-guard';
import { orderProposalLinkError, returnFromOrder, readOrderWorkspaceSection } from '../services/order-navigation';
import { loadOrderWorkspaceSection } from '../components/orders/order-workspace-loaders';
import { useManagerDocumentTitle } from '../services/manager-document-title';
import { navigateManager } from '../services/manager-navigation-history';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{ orderId: number; returnTo: string }>();
const order = ref<OrderWithResponsibility | null>(null);
useManagerDocumentTitle(computed(() => {
  const customer = order.value?.customer?.full_legal_name || order.value?.customer?.name;
  return `Заказ №${props.orderId}${customer ? ` · ${customer}` : ''}`;
}));
const workspace = ref<InstanceType<typeof OrderEditDrawer> | null>(null);
const loading = ref(false);
const error = ref('');
const proposalError = computed(() => order.value ? orderProposalLinkError(order.value, window.location.href) : '');
const backLabel = computed(() => props.returnTo.startsWith('/manager/calendar') ? 'К календарю' : 'К заказам');
let requestId = 0;
let deleted = false;
const scope = computed(() => `${managerSession.auth.value?.tenant_id}:${managerSession.auth.value?.staff_user_id || managerSession.auth.value?.username}:${managerStorefrontSelection.selectedSlug.value}`);
let mounted = false;
watch(scope, () => {
  requestId++; order.value = null; error.value = ''; loading.value = false;
  if (mounted && managerSession.isAuthenticated.value && !managerSession.recoveryRequired.value) void load();
}, { flush: 'sync' });
onScopeDispose(() => { requestId++; });
onScopeDispose(registerUnsavedNavigationGuard(() => deleted || !order.value || Boolean(proposalError.value) || (workspace.value?.prepareToLeave() ?? false)));
const load = async () => {
  const request = ++requestId;
  loading.value = true;
  error.value = '';
  try {
    const loaded = await api.getManagerOrderDetail(props.orderId);
    if (request === requestId) order.value = loaded;
  } catch (cause) {
    if (request === requestId) error.value = `Не удалось открыть заказ: ${getApiErrorMessage(cause)}`;
  } finally {
    if (request === requestId) loading.value = false;
  }
};
const back = () => returnFromOrder(props.returnTo);
const openCurrentProposal = () => {
  const url = new URL(window.location.href);
  url.searchParams.delete('proposalId');
  return navigateManager(`${url.pathname}${url.search}`, window.history.state, true);
};
const handleDeleted = () => { deleted = true; order.value = null; back(); };
onMounted(() => {
  mounted = true;
  window.scrollTo(0, 0);
  // Fetch the visible section code alongside the order, before its component mounts.
  void loadOrderWorkspaceSection(readOrderWorkspaceSection(window.location.href)).catch(() => {});
  void load();
});
</script>

<template>
  <section class="flex min-h-0 min-w-0 flex-1 flex-col" data-testid="order-page">
    <div v-if="!order || proposalError" class="mx-auto max-w-3xl p-4 sm:p-6">
      <button type="button" class="mb-5 inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-brand-700" @click="back"><ArrowLeft :size="18" />{{ backLabel }}</button>
      <div v-if="proposalError" role="alert"><p>{{ proposalError }}</p><button type="button" class="mt-4 rounded-lg border px-4 py-2" @click="openCurrentProposal">К актуальному предложению</button></div>
      <p v-else-if="loading" role="status" class="flex items-center gap-2"><Loader2 class="h-5 w-5 animate-spin" />Загружаем заказ…</p>
      <div v-else role="alert"><p>{{ error }}</p><button type="button" class="mt-4 rounded-lg border px-4 py-2" @click="load">Повторить</button></div>
    </div>
    <OrderEditDrawer v-if="!proposalError" ref="workspace" :model-value="Boolean(order)" :order="order" presentation="page" :back-label="backLabel" :form-error="error" @back="back" @updated="order = $event" @reload="load" @deleted="handleDeleted" />
  </section>
</template>
