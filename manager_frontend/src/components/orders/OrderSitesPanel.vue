<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref } from 'vue';
import { ChevronDown, ChevronUp, MapPin, Plus } from 'lucide-vue-next';
import {
  ManagerOrderSitesService,
  ManagerService,
  type ManagerCustomerBranchItemResponse,
  type OrderSiteAddRequest,
  type OrderSiteItem,
  type OrderSiteList,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import OrderSiteEquipmentPanel from './OrderSiteEquipmentPanel.vue';
import { loadOrderSitePages } from './order-site-pages';

const props = defineProps<{
  orderId: number;
  customerId: number;
  disabled: boolean;
  beforeAction: () => Promise<boolean>;
}>();
const emit = defineEmits<{ 'equipment-changed': [] }>();

const expanded = ref(false);
const section = ref<HTMLElement | null>(null);
const loaded = ref(false);
const loading = ref(false);
const readError = ref('');
const saveError = ref('');
const branchError = ref('');
const sites = ref<OrderSiteItem[]>([]);
const legacyPrimary = ref<OrderSiteList['legacy_primary']>(null);
const selectedId = ref<number | null>(null);
const selectedSite = computed(() => sites.value.find(site => site.id === selectedId.value));
const standalonePrimary = computed(() => {
  const primary = legacyPrimary.value;
  if (!primary) return null;
  const saved = sites.value.some(site => primary.customer_branch_id
    ? site.customer_branch_id === primary.customer_branch_id
    : site.address === primary.address);
  return saved ? null : primary;
});
const adding = ref(false);
const saving = ref(false);
const equipmentBusy = ref(false);
const branches = ref<ManagerCustomerBranchItemResponse[]>([]);
const branchLoading = ref(false);
const branchId = ref<number | null>(null);
const title = ref('');
const address = ref('');
const busy = computed(() => saving.value || equipmentBusy.value);
const canEdit = computed(() => !props.disabled && !busy.value && !loading.value);
const siteLabel = (site: OrderSiteItem) => site.title || site.address;
const availableBranches = computed(() => {
  const linked = new Set(sites.value.map(site => site.customer_branch_id));
  return branches.value.filter(branch => !linked.has(branch.id));
});
let active = true;
let branchRequest = 0;
let intent: { fingerprint: string; request: OrderSiteAddRequest } | undefined;
onScopeDispose(() => { active = false; });

const loadSites = async () => {
  if (loading.value) return;
  loading.value = true;
  readError.value = '';
  try {
    const items = await loadOrderSitePages((limit, offset) =>
      ManagerOrderSitesService.managerListOrderSites(props.orderId, limit, offset).then(page => {
        if (active && offset === 0) legacyPrimary.value = page.legacy_primary;
        return page;
      }),
    );
    if (!active) return;
    sites.value = items;
    if (!items.some(site => site.id === selectedId.value)) selectedId.value = items[0]?.id ?? null;
    loaded.value = true;
  } catch (error) {
    if (active) readError.value = 'Не удалось загрузить объекты. ' + getApiErrorMessage(error);
  } finally {
    if (active) loading.value = false;
  }
};
const toggle = () => {
  expanded.value = !expanded.value;
  if (expanded.value && !loaded.value) void loadSites();
};
const startAdd = async () => {
  adding.value = true;
  saveError.value = '';
  branchLoading.value = true;
  branchError.value = '';
  const request = ++branchRequest;
  try {
    const response = await ManagerService.getManagerCustomerBranches(props.customerId);
    if (active && request === branchRequest) branches.value = response.items;
  } catch (error) {
    if (active && request === branchRequest) branchError.value = 'Не удалось загрузить филиалы. ' + getApiErrorMessage(error);
  } finally {
    if (active && request === branchRequest) branchLoading.value = false;
  }
};
const clearAdd = () => {
  adding.value = false;
  branchRequest += 1;
  branchLoading.value = false;
  branchId.value = null;
  title.value = '';
  address.value = '';
  saveError.value = '';
};
const upsert = (site: OrderSiteItem) => {
  const current = sites.value.find(item => item.id === site.id);
  if (!current) sites.value = [...sites.value, site];
  else if (site.version >= current.version) {
    sites.value = sites.value.map(item => item.id === site.id ? site : item);
  }
};
const addSite = async (payload: OrderSiteAddRequest['payload']) => {
  if (!canEdit.value) return;
  saving.value = true;
  saveError.value = '';
  const fingerprint = JSON.stringify(payload);
  if (intent?.fingerprint !== fingerprint) {
    intent = { fingerprint, request: { payload, idempotency_key: crypto.randomUUID() } };
  }
  const request = intent.request;
  try {
    if (!await props.beforeAction() || !active) return;
    const { result } = await ManagerOrderSitesService.managerAddOrderSite(props.orderId, request);
    if (!active) return;
    upsert(result);
    selectedId.value = result.id;
    intent = undefined;
    clearAdd();
  } catch (error) {
    if (active) saveError.value = 'Не удалось добавить объект. ' + getApiErrorMessage(error);
  } finally {
    if (active) saving.value = false;
  }
};
const submit = () => {
  if (branchId.value) return addSite({ customer_branch_id: branchId.value });
  if (title.value.trim() && address.value.trim()) {
    return addSite({ title: title.value.trim(), address: address.value.trim() });
  }
};
const addPrimary = () => {
  const primary = standalonePrimary.value;
  if (!primary) return;
  if (primary.customer_branch_id) return addSite({ customer_branch_id: primary.customer_branch_id });
  if (primary.address) return addSite({ title: primary.title || 'Основной объект', address: primary.address });
};

onMounted(() => {
  const url = new URL(window.location.href);
  const candidate = Number(url.searchParams.get('orderSiteId'));
  if (url.pathname !== `/manager/orders/${props.orderId}` || !Number.isSafeInteger(candidate) || candidate <= 0) return;
  selectedId.value = candidate;
  expanded.value = true;
  void loadSites();
  void nextTick(() => section.value?.scrollIntoView?.({ block: 'start' }));
});
</script>

<template>
  <section id="order-workspace-sites" ref="section" class="min-w-0 scroll-mt-20 rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
    <button type="button" class="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60 sm:px-4" :aria-expanded="expanded" :disabled="busy" @click="toggle">
      <MapPin class="h-5 w-5 shrink-0 text-brand-700 dark:text-brand-300" />
      <span class="flex-1 text-sm font-semibold text-slate-900 dark:text-slate-100">Объекты заказа</span>
      <span v-if="loaded" class="text-xs text-slate-500">{{ sites.length }}</span>
      <component :is="expanded ? ChevronUp : ChevronDown" class="h-5 w-5 shrink-0 text-slate-500" />
    </button>

    <div v-if="expanded" class="space-y-3 border-t border-slate-200 p-3 dark:border-slate-700 sm:p-4">
      <p v-if="loading" role="status" class="text-sm text-slate-500">Загружаем объекты…</p>
      <p v-if="readError" role="alert" class="text-sm text-red-700 dark:text-red-300">
        {{ readError }}
        <button type="button" class="underline" :disabled="loading || busy" @click="loadSites">Повторить</button>
      </p>
      <template v-if="loaded">
        <div v-if="standalonePrimary" class="flex flex-wrap items-start justify-between gap-2 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/60">
          <div class="min-w-0 break-words">
            <p class="text-xs font-medium text-slate-500 dark:text-slate-400">Основной объект в карточке заказа</p>
            <p v-if="standalonePrimary.title">{{ standalonePrimary.title }}</p>
            <p v-if="standalonePrimary.address">{{ standalonePrimary.address }}</p>
          </div>
          <button v-if="!disabled && (standalonePrimary.customer_branch_id || standalonePrimary.address)" type="button" class="btn-mini-outline" :disabled="!canEdit || loading" @click="addPrimary">Добавить основной объект</button>
        </div>
        <div v-if="sites.length" class="flex flex-wrap items-end gap-2">
          <label class="field-label min-w-0 flex-1 basis-56">
            Объект
            <select v-model="selectedId" class="field-input" data-testid="order-site-select" :disabled="busy">
              <option v-for="site in sites" :key="site.id" :value="site.id">{{ siteLabel(site) }}</option>
            </select>
          </label>
          <button v-if="!adding && !disabled" type="button" class="btn-mini-outline" :disabled="!canEdit || loading" @click="startAdd"><Plus class="h-4 w-4" /> Добавить объект</button>
        </div>
        <div v-else-if="!adding" class="flex flex-wrap items-center justify-between gap-2">
          <p class="text-sm text-slate-500">Объекты для этого заказа ещё не добавлены.</p>
          <button v-if="!disabled" type="button" class="btn-mini-outline" :disabled="!canEdit || loading" @click="startAdd"><Plus class="h-4 w-4" /> Добавить объект</button>
        </div>

        <form v-if="adding" class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700" data-testid="add-order-site" @submit.prevent="submit">
          <fieldset class="space-y-3" :disabled="!canEdit">
            <label class="field-label">
              Филиал клиента
              <select v-model="branchId" class="field-input" :disabled="branchLoading">
                <option :value="null">Указать объект вручную</option>
                <option v-for="branch in availableBranches" :key="branch.id" :value="branch.id">
                  {{ [branch.name, branch.delivery_address].filter(Boolean).join(' · ') }}
                </option>
              </select>
            </label>
            <p v-if="branchLoading" role="status" class="text-xs text-slate-500">Загружаем филиалы…</p>
            <p v-if="branchError" role="alert" class="text-xs text-red-700 dark:text-red-300">{{ branchError }}</p>
            <div v-if="!branchId" class="grid gap-3 sm:grid-cols-2">
              <label class="field-label">Название<input v-model="title" class="field-input" maxlength="200" required /></label>
              <label class="field-label">Полный адрес<input v-model="address" class="field-input" maxlength="1000" required /></label>
            </div>
            <div class="flex flex-wrap justify-end gap-2">
              <button type="button" class="btn-mini-outline" @click="clearAdd">Отмена</button>
              <button type="submit" class="btn-mini" :disabled="!branchId && !(title.trim() && address.trim())">{{ saving ? 'Добавляем…' : 'Добавить' }}</button>
            </div>
          </fieldset>
        </form>
        <p v-if="saveError" role="alert" class="break-words text-sm text-red-700 dark:text-red-300">{{ saveError }}</p>
        <OrderSiteEquipmentPanel
          v-if="selectedSite"
          :key="selectedSite.id"
          :site="selectedSite"
          :customer-id="customerId"
          :disabled="disabled || saving || loading"
          :before-action="beforeAction"
          @busy="equipmentBusy = $event"
          @site-updated="upsert"
          @stale="loadSites"
          @equipment-changed="emit('equipment-changed')"
        />
      </template>
    </div>
  </section>
</template>
