<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../../api';
import { useCompanyAddressSuggestion } from '../../composables/useCompanyAddressSuggestion';
import type {
  ManagerCatalogCustomerItemResponse,
  ManagerCustomerBranchItemResponse,
  ManagerOrderDetailResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import OrderCustomerObjectSummary from './OrderCustomerObjectSummary.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';
import CustomerSearchSelect from '../customers/CustomerSearchSelect.vue';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  addressError?: string;
  commentError?: string;
  beforeNavigate?: () => Promise<boolean>;
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
const searchedCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);
const assigningCustomer = ref(false);
const {
  candidates: companyAddressCandidates,
  loading: companyAddressLoading,
  error: companyAddressError,
  searched: companyAddressSearched,
  suggest: requestCompanyAddressSuggestion,
  reset: resetCompanyAddressSuggestion,
} = useCompanyAddressSuggestion();
let branchesRequestId = 0;

const customer = computed(() => props.order.customer ?? null);
const companyName = computed(() => (
  customer.value?.full_legal_name?.trim() || customer.value?.name?.trim() || ''
));
const canSuggestCompanyAddress = computed(() => (
  customer.value?.type === 'company' && !deliveryAddress.value.trim() && Boolean(companyName.value)
));
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

const loadBranches = async (customerId: number) => {
  const requestId = ++branchesRequestId;
  branchesLoading.value = true;
  try {
    const response = await api.getManagerCustomerBranches(customerId);
    if (requestId !== branchesRequestId) return;
    branches.value = response.items || [];
    // Loading choices never changes the order. Hydration owns the saved branch;
    // only a manager selection or branch creation may change its model.
  } catch (error) {
    if (requestId !== branchesRequestId) return;
    console.error('Failed to load customer branches', error);
    // A lookup failure must not detach the order from its saved object.
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

const openCustomerProfile = async () => {
  if (!customer.value?.id) return;
  const returnTo = `${window.location.pathname}${window.location.search}`;
  const query = new URLSearchParams({
    customerId: String(customer.value.id),
    returnTo,
  });
  if (props.beforeNavigate && !await props.beforeNavigate()) return;
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

const assignCustomer = async (newCustomer: ManagerCatalogCustomerItemResponse) => {
  if (assigningCustomer.value) return;
  assigningCustomer.value = true;
  try {
    const updated = await api.patchManagerOrder(props.order.id, { customer_id: newCustomer.id });
    showCustomerSearch.value = false;
    searchedCustomer.value = null;
    emit('updated', updated);
    emit('reload', updated.id);
    notify('Клиент успешно изменен', 'success');
  } catch (error) {
    searchedCustomer.value = null;
    notify(`Ошибка смены клиента: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    assigningCustomer.value = false;
  }
};

const openCustomerSearch = () => {
  searchedCustomer.value = null;
  showCustomerSearch.value = true;
};

const closeCustomerSearch = () => {
  if (assigningCustomer.value) return;
  showCustomerSearch.value = false;
  searchedCustomer.value = null;
};

const suggestCompanyAddress = () => {
  if (!canSuggestCompanyAddress.value) return;
  void requestCompanyAddressSuggestion(companyName.value);
};

const chooseCompanyAddress = (address: string) => {
  const value = address.trim();
  if (!value) return;
  deliveryAddress.value = value;
  resetCompanyAddressSuggestion();
};

watch(
  () => [props.order.id, props.order.customer?.id, props.order.customer_branch?.id],
  () => {
    showCustomerSearch.value = false;
    searchedCustomer.value = null;
    assigningCustomer.value = false;
    const customerId = props.order.customer?.id;
    if (customerId) void loadBranches(customerId);
    else resetBranches();
    resetCompanyAddressSuggestion();
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
    @change-customer="openCustomerSearch"
    @toggle-branch="showBranchFields = !showBranchFields"
  />

  <div v-if="canSuggestCompanyAddress" class="mt-2 px-3 text-sm text-slate-600 dark:text-slate-300">
    <p>Адрес объекта не указан. Можно найти его по названию компании.</p>
    <button
      type="button"
      data-testid="suggest-company-address"
      class="btn-mini-outline mt-2 text-xs"
      :disabled="companyAddressLoading"
      @click="suggestCompanyAddress"
    >{{ companyAddressLoading ? 'Ищем адрес...' : 'Подобрать адрес' }}</button>
    <p v-if="companyAddressError" class="mt-2 text-xs text-red-700">Не удалось получить подсказки. Адрес можно ввести вручную.</p>
    <p v-else-if="companyAddressSearched && !companyAddressLoading && companyAddressCandidates.length === 0" class="mt-2 text-xs text-slate-500 dark:text-slate-400">Подходящих подсказок не найдено. Адрес можно ввести вручную.</p>
    <div v-else-if="companyAddressCandidates.length" class="mt-2 space-y-1">
      <p class="text-xs text-slate-500 dark:text-slate-400">Выберите подходящий адрес объекта:</p>
      <button
        v-for="candidate in companyAddressCandidates"
        :key="candidate.value"
        type="button"
        :data-testid="`company-address-candidate-${candidate.value}`"
        class="block w-full rounded-md border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 px-2 py-1.5 text-left text-sm hover:border-brand-500"
        @click="chooseCompanyAddress(candidate.value)"
      >
        <span class="font-medium">{{ candidate.value }}</span>
        <span v-if="candidate.subtitle" class="block text-xs text-slate-500">{{ candidate.subtitle }}</span>
      </button>
    </div>
  </div>

  <div v-if="showBranchFields && customer?.id" class="mt-2 grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900 sm:grid-cols-2">
    <label class="field-label sm:col-span-2">
      Филиал клиента
      <select :value="customerBranchId ?? ''" data-testid="customer-branch" class="field-input mt-1" :disabled="branchesLoading" @change="onBranchChange">
        <option value="">Без филиала</option>
        <option v-if="customerBranchId && !branches.some((branch) => branch.id === customerBranchId)" :value="customerBranchId">
          {{ selectedBranch?.name || `Филиал #${customerBranchId}` }} — {{ selectedBranch?.delivery_address || deliveryAddress }}
        </option>
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
    <div v-if="showCustomerSearch" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" @click.self="closeCustomerSearch">
      <div class="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900">
        <div class="flex items-center justify-between border-b border-gray-100 bg-slate-50/50 px-6 py-4 shadow-sm">
          <h3 class="flex items-center gap-2 text-lg font-bold text-slate-800"><span class="material-icons-round text-slate-500">swap_horiz</span>Сменить клиента для заказа</h3>
          <button class="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-colors hover:bg-slate-200 disabled:opacity-50" :disabled="assigningCustomer" @click="closeCustomerSearch"><span class="material-icons-round text-[18px]">close</span></button>
        </div>
        <div class="overflow-y-auto p-6">
          <CustomerSearchSelect v-model="searchedCustomer" result-test-id-prefix="assign-customer" :disabled="assigningCustomer" @update:model-value="(customer) => customer && assignCustomer(customer)" />
        </div>
        <div class="flex justify-end border-t border-gray-100 bg-slate-50/50 px-6 py-4"><button class="rounded-xl px-5 py-2 font-medium text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-800 disabled:opacity-50" :disabled="assigningCustomer" @click="closeCustomerSearch">Отмена</button></div>
      </div>
    </div>
  </Transition>
</template>
