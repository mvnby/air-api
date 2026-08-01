<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import type {
  ManagerCatalogCustomerItemResponse,
  ManagerCustomerBranchItemResponse,
  ManagerOrderDetailResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import OrderCustomerObjectSummary from './OrderCustomerObjectSummary.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  addressError?: string;
  commentError?: string;
}>();

const emit = defineEmits<{
  toast: [payload: { message: string; type: 'success' | 'error' }];
  updated: [order: ManagerOrderDetailResponse];
  reload: [orderId: number];
}>();

const deliveryAddress = defineModel<string>('deliveryAddress', { required: true });
const customerBranchId = defineModel<number | null>('customerBranchId', { required: true });
const comment = defineModel<string>('comment', { required: true });
const expanded = defineModel<boolean>('expanded', { required: true });
const newBranchAddress = defineModel<string>('newBranchAddress', { required: true });

const branches = ref<ManagerCustomerBranchItemResponse[]>([]);
const branchesLoading = ref(false);
const creatingBranch = ref(false);
const newBranchName = ref('');
const showBranchFields = ref(false);
const savingCustomer = ref(false);
const showCustomerSearch = ref(false);
const customerSearchQuery = ref('');
const customerSearchResults = ref<ManagerCatalogCustomerItemResponse[]>([]);
const customerSearchLoading = ref(false);
let branchesRequestId = 0;
let customerSearchRequestId = 0;

const customer = computed(() => props.order.customer ?? null);
const selectedBranch = computed(() => (
  branches.value.find((branch) => branch.id === customerBranchId.value)
  || props.order.customer_branch
  || null
));
const objectAddress = computed(() => (
  deliveryAddress.value.trim() || selectedBranch.value?.delivery_address || ''
));
const sectionSummary = computed(() => (
  customerBranchId.value ? 'Филиал и дополнительные данные' : 'Адрес и комментарий'
));

const notify = (message: string, type: 'success' | 'error') => {
  emit('toast', { message, type });
};

const resetBranches = () => {
  branchesRequestId += 1;
  branches.value = [];
  customerBranchId.value = null;
  branchesLoading.value = false;
  creatingBranch.value = false;
  newBranchName.value = '';
  newBranchAddress.value = '';
};

const loadBranches = async (customerId: number, preferredBranchId?: number | null) => {
  const requestId = ++branchesRequestId;
  branchesLoading.value = true;
  try {
    const response = await api.getManagerCustomerBranches(customerId);
    if (requestId !== branchesRequestId) return;
    branches.value = response.items || [];
    if (!branches.value.length || preferredBranchId === null) {
      customerBranchId.value = null;
      return;
    }
    const preferredFromOrder = typeof preferredBranchId === 'number'
      ? branches.value.find((branch) => branch.id === preferredBranchId)
      : null;
    const preferred = preferredFromOrder
      || branches.value.find((branch) => branch.is_default)
      || branches.value[0]
      || null;
    customerBranchId.value = preferred?.id || null;
  } catch (error) {
    if (requestId !== branchesRequestId) return;
    console.error('Failed to load customer branches', error);
    resetBranches();
  } finally {
    if (requestId === branchesRequestId) branchesLoading.value = false;
  }
};

const onBranchChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value;
  customerBranchId.value = value ? Number(value) : null;
  const branch = branches.value.find((item) => item.id === customerBranchId.value) || null;
  if (branch) deliveryAddress.value = branch.delivery_address;
};

const createBranch = async () => {
  const customerId = customer.value?.id;
  if (!customerId || creatingBranch.value) return;
  const address = newBranchAddress.value.trim();
  if (!address) {
    notify('Введите адрес филиала', 'error');
    return;
  }
  creatingBranch.value = true;
  try {
    const created = await api.createManagerCustomerBranch(customerId, {
      name: newBranchName.value.trim() || undefined,
      delivery_address: address,
      is_default: branches.value.length === 0,
    });
    branches.value = [created, ...branches.value.filter((branch) => branch.id !== created.id)];
    customerBranchId.value = created.id;
    deliveryAddress.value = created.delivery_address;
    newBranchName.value = '';
    newBranchAddress.value = '';
    notify('Филиал создан', 'success');
  } catch (error) {
    notify(`Ошибка создания филиала: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    creatingBranch.value = false;
  }
};

const copyText = async (value: string | null | undefined, label: string) => {
  const normalized = String(value || '').trim();
  if (!normalized) {
    notify(`${label} отсутствует`, 'error');
    return;
  }
  try {
    await navigator.clipboard.writeText(normalized);
    notify(`${label} скопирован`, 'success');
  } catch {
    notify(`Не удалось скопировать ${label.toLowerCase()}`, 'error');
  }
};

const openCustomerProfile = () => {
  if (!customer.value?.id) return;
  const returnTo = `${window.location.pathname}${window.location.search}`;
  const query = new URLSearchParams({
    customerId: String(customer.value.id),
    returnTo,
  });
  window.history.pushState({}, '', `/manager/customers/profile?${query.toString()}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const saveCustomer = async (payload: { name: string; phone: string; email: string }) => {
  const customerId = customer.value?.id;
  if (!customerId || savingCustomer.value) return;
  savingCustomer.value = true;
  try {
    await api.patchManagerCustomer(customerId, {
      name: payload.name,
      full_legal_name: customer.value?.type === 'company' ? payload.name : undefined,
      phone: payload.phone || null,
      email: payload.email || null,
    });
    notify('Контакты клиента обновлены', 'success');
    emit('reload', props.order.id);
  } catch (error) {
    notify(`Не удалось обновить клиента: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    savingCustomer.value = false;
  }
};

const debouncedSearchCustomer = useDebounceFn(async (query: string) => {
  const requestId = ++customerSearchRequestId;
  if (query.length < 3) {
    customerSearchResults.value = [];
    customerSearchLoading.value = false;
    return;
  }
  customerSearchLoading.value = true;
  try {
    const response = await api.getManagerCustomers(1, 10, query);
    if (requestId !== customerSearchRequestId || query !== customerSearchQuery.value) return;
    customerSearchResults.value = response.items || [];
  } catch (error) {
    if (requestId === customerSearchRequestId) console.error('Customer search error', error);
  } finally {
    if (requestId === customerSearchRequestId) customerSearchLoading.value = false;
  }
}, 400);

const assignCustomer = async (newCustomer: ManagerCatalogCustomerItemResponse) => {
  try {
    const updated = await api.patchManagerOrder(props.order.id, { customer_id: newCustomer.id });
    showCustomerSearch.value = false;
    emit('updated', updated);
    emit('reload', updated.id);
    notify('Клиент успешно изменен', 'success');
  } catch (error) {
    notify(`Ошибка смены клиента: ${getApiErrorMessage(error)}`, 'error');
  }
};

watch(
  () => [props.order.id, props.order.customer?.id, props.order.customer_branch?.id],
  () => {
    const customerId = props.order.customer?.id;
    if (customerId) void loadBranches(customerId, props.order.customer_branch?.id ?? null);
    else resetBranches();
  },
  { immediate: true },
);
</script>

<template>
  <OrderCustomerObjectSummary
    :customer="customer"
    :branch="selectedBranch"
    :address="objectAddress"
    :has-comment="Boolean(comment.trim())"
    :saving-customer="savingCustomer"
    @copy="copyText"
    @save-customer="saveCustomer"
    @update:address="deliveryAddress = $event"
    @open-customer="openCustomerProfile"
    @change-customer="showCustomerSearch = true"
    @toggle-branch="showBranchFields = !showBranchFields"
  />

  <div v-if="showBranchFields && customer?.id" class="mt-2 grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900 sm:grid-cols-2">
    <label class="field-label sm:col-span-2">
      Филиал клиента
      <select :value="customerBranchId ?? ''" data-testid="customer-branch" class="field-input mt-1" :disabled="branchesLoading" @change="onBranchChange">
        <option value="">Без филиала</option>
        <option v-for="branch in branches" :key="branch.id" :value="branch.id">{{ branch.name || `Филиал #${branch.id}` }} — {{ branch.delivery_address }}</option>
      </select>
    </label>
    <input v-model="newBranchName" class="field-input" placeholder="Название нового филиала" />
    <AddressSuggestInput v-model="newBranchAddress" placeholder="Адрес нового филиала" />
    <div class="flex justify-end sm:col-span-2">
      <button type="button" class="btn-mini-outline text-xs" :disabled="creatingBranch" @click="createBranch">{{ creatingBranch ? 'Создаём...' : 'Создать и выбрать' }}</button>
    </div>
  </div>

  <slot />

  <OrderDrawerSection
    id="order-workspace-object"
    v-model:expanded="expanded"
    title="Подробнее об объекте"
    :summary="sectionSummary"
    tone="default"
    :has-error="Boolean(addressError || commentError)"
  >
    <div class="grid gap-3 md:grid-cols-2">
      <AddressSuggestInput v-model="deliveryAddress" class="md:col-span-2" label="Адрес объекта / доставки" placeholder="Введите адрес..." :error="addressError" />
      <label class="field-label md:col-span-2">
        Комментарий
        <textarea v-model="comment" class="field-input min-h-[90px]" :class="commentError ? 'border-red-500 focus:outline-red-400' : ''" />
        <span v-if="commentError" class="text-xs text-red-300">{{ commentError }}</span>
      </label>
    </div>
  </OrderDrawerSection>

  <Transition name="fade">
    <div v-if="showCustomerSearch" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" @click.self="showCustomerSearch = false">
      <div class="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b border-gray-100 bg-slate-50/50 px-6 py-4 shadow-sm">
          <h3 class="flex items-center gap-2 text-lg font-bold text-slate-800"><span class="material-icons-round text-slate-500">swap_horiz</span>Сменить клиента для заказа</h3>
          <button class="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-colors hover:bg-slate-200" @click="showCustomerSearch = false"><span class="material-icons-round text-[18px]">close</span></button>
        </div>
        <div class="overflow-y-auto p-6">
          <div class="relative mb-4">
            <span class="material-icons-round absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">search</span>
            <input v-model="customerSearchQuery" data-testid="customer-search" type="text" class="w-full rounded-xl border-none bg-slate-50 py-3 pl-11 pr-4 text-sm transition-shadow focus:ring-2 focus:ring-teal-500" placeholder="Поиск по телефону, УНП, имени..." autofocus @input="debouncedSearchCustomer(customerSearchQuery)" />
            <span v-if="customerSearchLoading" class="material-icons-round absolute right-4 top-1/2 -translate-y-1/2 animate-spin text-teal-500">refresh</span>
          </div>
          <div v-if="customerSearchQuery.length >= 3 && !customerSearchResults.length && !customerSearchLoading" class="rounded-xl border border-dashed border-slate-100 bg-slate-50 py-6 text-center text-sm text-slate-500">Клиенты не найдены</div>
          <div v-if="customerSearchQuery.length < 3" class="py-6 text-center text-xs font-semibold uppercase tracking-wider text-slate-400">Введите минимум 3 символа</div>
          <div class="mt-2 space-y-2">
            <button v-for="result in customerSearchResults" :key="result.id" type="button" :data-testid="`assign-customer-${result.id}`" class="group flex w-full flex-col gap-1 rounded-xl border border-slate-100 bg-white p-4 text-left outline-none transition-all hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-md focus:ring-2 focus:ring-teal-500" @click="assignCustomer(result)">
              <span class="text-sm font-bold text-slate-800 transition-colors group-hover:text-teal-700">{{ result.full_legal_name || result.name || `Клиент #${result.id}` }}</span>
              <span class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500"><span v-if="result.phone">{{ result.phone }}</span><span v-if="result.inn">УНП: {{ result.inn }}</span></span>
            </button>
          </div>
        </div>
        <div class="flex justify-end border-t border-gray-100 bg-slate-50/50 px-6 py-4"><button class="rounded-xl px-5 py-2 font-medium text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-800" @click="showCustomerSearch = false">Отмена</button></div>
      </div>
    </div>
  </Transition>
</template>
