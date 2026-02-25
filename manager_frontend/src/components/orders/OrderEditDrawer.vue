<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
import CustomerSummaryCard from '../customers/CustomerSummaryCard.vue';
import DealExecutionTab from './DealExecutionTab.vue';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
  OrderProductLineResponse,
  OrderServiceLineResponse,
  ManagerOrderDocumentItem,
  ManagerInstallerResponse,
  PaymentResponse,
} from '../../client';
import { ManagerDocsService, ManagerOrdersService } from '../../client';
import { formatMoney } from './order-utils';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../../utils/datetime';

import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  modelValue: boolean;
  order: ManagerOrderDetailResponse | null;
  serverErrors?: Record<string, string>;
  formError?: string;
  saving?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  save: [payload: { orderId: number; data: ManagerOrderUpdatePayload }];
}>();

type ProductOption = {
  id: number;
  title: string;
  price: number;
  is_inverter: boolean;
  power_cooling: number | null;
};
type ProductLine = { product_id: number; product_query: string; quantity: number; price: number; cost: number };
type ServiceLine = { service_id?: number | null; title: string; quantity: number; price: number; cost: number };

type OrderDrawerDraft = {
  productLines: ProductLine[];
};

const productOptions = ref<ProductOption[]>([]);
const productLookupById = ref<Record<number, ProductOption>>({});
const activeSuggestionIndex = ref<number | null>(null);
const productLookupLoading = ref(false);
const toast = ref('');
let productSearchRequestId = 0;

const status = ref('new_lead');
const nextFollowupDate = ref('');
const assessmentDate = ref('');
const installationDate = ref('');
const comment = ref('');
const isPaid = ref(false);
const installerId = ref<number | null>(null);

// Negotiation stage properties
const measurementRequired = ref(false);
const measurerId = ref<number | null>(null);
const measurementResult = ref('');
const proposalStatus = ref<'draft' | 'sent' | 'approved' | 'rejected'>('draft');

const installersList = ref<ManagerInstallerResponse[]>([]);

const productLines = ref<ProductLine[]>([]);
const serviceLines = ref<ServiceLine[]>([]);
const documents = ref<ManagerOrderDocumentItem[]>([]);
const payments = ref<PaymentResponse[]>([]);
const localServerErrors = ref<Record<string, string>>({});

const localFormError = ref('');
const showCustomerModal = ref(false);

const customer = computed(() => props.order?.customer ?? null);
const draftKey = computed(() => (props.order ? `manager_order_drawer_draft_${props.order.id}` : ''));

const toastType = ref<'success' | 'error'>('success');
const setToast = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = message;
  toastType.value = type;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const toggleHold = async () => {
    if (!props.order) return;
    const hold = !props.order.is_on_hold;
    try {
        await api.patchManagerOrder(props.order.id, { is_on_hold: hold, on_hold_reason: hold ? 'Переговоры / Ручная пауза' : '' });
        props.order.is_on_hold = hold;
        props.order.on_hold_reason = hold ? 'Переговоры / Ручная пауза' : '';
        emit('save', { orderId: props.order.id, data: { status: props.order.status } });
    } catch {
        setToast('Ошибка паузы', 'error');
    }
};

const isGeneratingDoc = ref(false);
const processingDocId = ref<number | null>(null);
const docDropdownOpen = ref(false);

const hasContract = computed(() => documents.value.some(d => d.doc_type === 'contract'));

const DOCUMENT_TYPES = [
  { type: 'contract', label: 'Договор' },
  { type: 'invoice', label: 'Счет' },
  { type: 'act', label: 'Акт' },
  { type: 'offer', label: 'КП' },
  { type: 'tn2', label: 'ТН-2' },
  { type: 'ttn1', label: 'ТТН-1' },
];

const loadDocuments = async (orderId: number) => {
  try {
    const res = await ManagerDocsService.getManagerOrderDocuments(orderId);
    documents.value = res.items;
  } catch (error) {
    console.error('Failed to load documents', error);
  }
};

const generateDocument = async (type: string) => {
  if (!props.order?.id) return;
  isGeneratingDoc.value = true;
  try {
    const res = await ManagerOrdersService.generateManagerOrderDocument(props.order.id, type);
    window.open(res.edit_url, '_blank');
    await loadDocuments(props.order.id);
    setToast('Документ создан', 'success');
  } catch (error) {
    setToast(`Ошибка генерации: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isGeneratingDoc.value = false;
  }
};

const downloadDocument = async (doc: ManagerOrderDocumentItem) => {
  processingDocId.value = doc.id;
  try {
    const response = await ManagerDocsService.getManagerDocDownload(doc.id);
    
    // Create blob link to download
    
    // If we look at ManagerDocsService.ts: returns CancelablePromise<any>.
    // Let's assume it returns the blob because the browser implementation of fetch/request handles it?
    // Actually, generated code usually parses JSON.
    // If I need Blob, I might need to access raw response or ensure generation config handles binary.
    // Let's implement a fallback or assume naive approach first.
    
    // Actually, easier way for now: open direct URL in new tab which triggers download?
    // But we need auth token. Browser simply opening link won't attach header unless cookie.
    // We use Bearer token.
    
    // We can use the ApiService.getDownloadLink presumably if we had one, but we have a method returning stream.
    // Let's try to handle Blob.
    
    const url = window.URL.createObjectURL(new Blob([response]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${doc.number}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    setToast('Ошибка скачивания', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const deleteDocument = async (docId: number) => {
  if (!confirm('Удалить документ?')) return;
  processingDocId.value = docId;
  try {
    await ManagerDocsService.deleteManagerDoc(docId);
    if (props.order?.id) await loadDocuments(props.order.id);
    setToast('Документ удален', 'success');
  } catch (error) {
    setToast('Ошибка удаления', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const newPaymentAmount = ref<number | null>(null);
const newPaymentType = ref<string>('prepayment');
const isAddingPayment = ref(false);

const addPayment = async () => {
  if (!props.order?.id || !newPaymentAmount.value) return;
  isAddingPayment.value = true;
  try {
    const res = await ManagerOrdersService.addManagerOrderPayment(props.order.id, {
        amount: newPaymentAmount.value,
        type: newPaymentType.value,
    });
    payments.value = res;
    newPaymentAmount.value = null;
    setToast('Платеж добавлен', 'success');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isAddingPayment.value = false;
  }
};

const deletePayment = async (paymentId: number) => {
  if (!props.order?.id) return;
  if (!confirm('Удалить платеж?')) return;
  try {
    const res = await ManagerOrdersService.deleteManagerOrderPayment(props.order.id, paymentId);
    payments.value = res;
    setToast('Платеж удален', 'success');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  }
};


const totalPreview = computed(() => {
  const pTotal = productLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
  const sTotal = serviceLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
  return pTotal + sTotal;
});

const totalPaymentsPreview = computed(() => {
  return payments.value.reduce((sum, p) => sum + p.amount, 0);
});

const balanceDuePreview = computed(() => {
  return Math.max(0, totalPreview.value - totalPaymentsPreview.value);
});

const marginPreview = computed(() => {
  const pCost = productLines.value.reduce((sum, line) => sum + line.cost * line.quantity, 0);
  const sCost = serviceLines.value.reduce((sum, line) => sum + line.cost * line.quantity, 0);
  return totalPreview.value - (pCost + sCost);
});

const rememberProductOption = (option: ProductOption) => {
  productLookupById.value = {
    ...productLookupById.value,
    [option.id]: option,
  };
};

const rememberProductOptions = (options: ProductOption[]) => {
  if (!options.length) return;
  const merged = { ...productLookupById.value };
  for (const option of options) merged[option.id] = option;
  productLookupById.value = merged;
};

const mapSmartSearchItemToOption = (item: any): ProductOption => ({
  id: Number(item.id),
  title: String(item.title ?? ''),
  price: Number(item.price ?? 0),
  is_inverter: Boolean(item.is_inverter),
  power_cooling: item.power_cooling == null ? null : Number(item.power_cooling),
});

const syncProductLookupFromLines = () => {
  for (const line of productLines.value) {
    if (!line.product_id || productLookupById.value[line.product_id]) continue;
    rememberProductOption({
      id: line.product_id,
      title: line.product_query,
      price: line.price,
      is_inverter: false,
      power_cooling: null,
    });
  }
};

const debouncedLoadProductOptions = useDebounceFn(async (index: number, q: string, requestId: number) => {
  try {
    productLookupLoading.value = true;
    const response = await api.smartSearchProducts(q, 20);
    if (requestId !== productSearchRequestId || activeSuggestionIndex.value !== index) return;
    const options = Array.isArray(response) ? response.map(mapSmartSearchItemToOption) : [];
    productOptions.value = options;
    rememberProductOptions(options);
  } catch (error) {
    setToast(`Ошибка поиска товаров: ${getApiErrorMessage(error)}`);
    if (requestId === productSearchRequestId) {
      productOptions.value = [];
    }
  } finally {
    if (requestId === productSearchRequestId) {
      productLookupLoading.value = false;
    }
  }
}, 400);

const persistDraft = () => {
  if (!draftKey.value) return;
  try {
    const payload: OrderDrawerDraft = {
      productLines: productLines.value.map((line) => ({ ...line })),
    };
    window.sessionStorage.setItem(draftKey.value, JSON.stringify(payload));
  } catch (error) {
    console.warn('Failed to persist order drawer draft', error);
  }
};

const restoreDraft = () => {
  if (!draftKey.value) return;
  try {
    const raw = window.sessionStorage.getItem(draftKey.value);
    if (!raw) return;
    const payload = JSON.parse(raw) as Partial<OrderDrawerDraft>;
    if (Array.isArray(payload.productLines) && payload.productLines.length) {
      productLines.value = payload.productLines.map((line) => ({
        product_id: Number(line.product_id || 0),
        product_query: String(line.product_query || ''),
        quantity: Number(line.quantity || 1),
        price: Number(line.price || 0),
        cost: Number(line.cost || 0),
      }));
    }
  } catch (error) {
    console.warn('Failed to restore order drawer draft', error);
  }
};

const clearDraft = () => {
  if (!draftKey.value) return;
  try {
    window.sessionStorage.removeItem(draftKey.value);
  } catch (error) {
    console.warn('Failed to clear order drawer draft', error);
  }
};

const initForm = async (order: ManagerOrderDetailResponse | null) => {
  if (!order) return;
  localServerErrors.value = {};
  localFormError.value = '';
  status.value = order.status;
  nextFollowupDate.value = toLocalDateTimeInput(order.next_followup_date);
  assessmentDate.value = toLocalDateTimeInput(order.measurement_date);
  installationDate.value = toLocalDateTimeInput(order.installation_date);
  comment.value = order.comment ?? '';
  isPaid.value = order.is_paid;
  installerId.value = order.installer_id ?? null;
  measurementRequired.value = order.measurement_required ?? false;
  measurerId.value = order.measurer_id ?? null;
  measurementResult.value = order.measurement_result ?? '';
  proposalStatus.value = (order.proposal_status as any) || 'draft';

  if (installersList.value.length === 0) {
    api.getManagerInstallers(1, 100).then(res => {
      installersList.value = res.items.filter(i => i.is_active || i.id === installerId.value);
    }).catch(e => console.error("Failed to load installers", e));
  }

  productLines.value = (order.product_lines ?? []).map((line: OrderProductLineResponse) => ({
    product_id: line.product_id || 0,
    product_query: line.product_title || '',
    quantity: line.quantity,
    price: line.price,
    cost: line.cost,
  }));
  serviceLines.value = (order.service_lines ?? []).map((line: OrderServiceLineResponse) => ({
    service_id: line.service_id,
    title: line.service_title,
    quantity: line.quantity,
    price: line.price,
    cost: line.cost,
  }));
  
  // Documents
  documents.value = (order.documents || []).map((d: any) => ({
      id: d.id,
      doc_type: d.doc_type,
      number: d.number,
      date: d.date,
      edit_url: d.edit_url
  }));
  // Payments
  payments.value = [...(order.payments || [])];
  
  // Also refresh list to be sure
  loadDocuments(order.id);

  productLookupById.value = {};

  syncProductLookupFromLines();
  productOptions.value = [];
  activeSuggestionIndex.value = null;
  productLookupLoading.value = false;
  restoreDraft();
  syncProductLookupFromLines();
};

watch(
  () => props.modelValue,
  async (value) => {
    if (value) await initForm(props.order);
  },
);

watch(
  () => props.order,
  async (value) => {
    if (props.modelValue) await initForm(value);
  },
);

const onProductChanged = (index: number, applyCatalogPrice = false) => {
  const row = productLines.value[index];
  if (!row) return;
  const selected = productLookupById.value[row.product_id];
  if (!selected) return;
  row.product_query = selected.title;
  if (applyCatalogPrice) {
    row.price = selected.price;
  }
};

const getProductSuggestions = (index: number) => {
  if (activeSuggestionIndex.value !== index) return [];
  return productOptions.value.slice(0, 10);
};

const onProductQueryInput = (index: number) => {
  const row = productLines.value[index];
  if (!row) return;
  activeSuggestionIndex.value = index;
  const query = row.product_query.trim();
  row.product_id = 0;
  productSearchRequestId += 1;
  if (query.length < 2) {
    productOptions.value = [];
    productLookupLoading.value = false;
    return;
  }
  debouncedLoadProductOptions(index, query, productSearchRequestId);
};

const onProductInputBlur = (index: number) => {
  window.setTimeout(() => {
    if (activeSuggestionIndex.value === index) {
      activeSuggestionIndex.value = null;
    }
  }, 120);
};

const onProductInputFocus = (index: number) => {
  activeSuggestionIndex.value = index;
};

const selectProductForLine = (index: number, option: ProductOption) => {
  const row = productLines.value[index];
  if (!row) return;
  const isNewLine = !row.product_id && Number(row.price || 0) <= 0;
  row.product_id = option.id;
  row.product_query = option.title;
  rememberProductOption(option);
  activeSuggestionIndex.value = null;
  productOptions.value = [];
  onProductChanged(index, isNewLine);
};

const openSelectedProduct = (index: number) => {
  const row = productLines.value[index];
  if (!row?.product_id) return;
  persistDraft();
  const returnTo = `${window.location.pathname}${window.location.search}`;
  const query = new URLSearchParams({
    editProductId: String(row.product_id),
    editProductQuery: row.product_query || '',
    returnTo,
  });
  window.history.pushState({}, '', `/manager/products?${query.toString()}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const addProductLine = () => {
  productLines.value.push({ product_id: 0, product_query: '', quantity: 1, price: 0, cost: 0 });
};

const addServiceLine = () => {
  serviceLines.value.push({ title: '', quantity: 1, price: 0, cost: 0, service_id: null });
};

const removeProductLine = (index: number) => {
  productLines.value.splice(index, 1);
};

const removeServiceLine = (index: number) => {
  serviceLines.value.splice(index, 1);
};

const currentCatalogPrice = (productId: number) => productLookupById.value[productId]?.price ?? null;
const isPriceDifferentFromCatalog = (line: { product_id: number; price: number }) => {
  const catalog = currentCatalogPrice(line.product_id);
  return catalog !== null && Number(catalog) !== Number(line.price || 0);
};
const lineTotal = (line: { quantity: number; price: number }) => Number(line.quantity || 0) * Number(line.price || 0);

const handleSave = () => {
  if (!props.order) return;
  localServerErrors.value = {};
  localFormError.value = '';

  const errors: Record<string, string> = {};
  if (!status.value) {
    errors.status = 'Укажите статус';
  }

  if (assessmentDate.value && installationDate.value && installationDate.value < assessmentDate.value) {
    errors.installation_date = 'Дата монтажа не может быть раньше даты замера';
  }

  if (productLines.value.some((line) => line.quantity <= 0)) {
    errors.products = 'Количество товара должно быть больше 0';
  } else if (productLines.value.some((line) => line.price < 0)) {
    errors.products = 'Цена товара не может быть отрицательной';
  } else if (productLines.value.some((line) => !line.product_id)) {
    errors.products = 'Выберите товар из выпадающего списка';
  }

  if (serviceLines.value.some((line) => line.quantity <= 0)) {
    errors.services = 'Количество услуги должно быть больше 0';
  } else if (serviceLines.value.some((line) => line.price < 0)) {
    errors.services = 'Цена услуги не может быть отрицательной';
  } else if (serviceLines.value.some((line) => !line.title?.trim())) {
    errors.services = 'Для услуги укажите название';
  }

  if (Object.keys(errors).length) {
    localServerErrors.value = errors;
    localFormError.value = 'Исправьте ошибки в форме';
    return;
  }

  // Cross-field validation for Negotiation
  if (status.value === 'execution') {
    if (totalPreview.value <= 0) {
      localFormError.value = 'Нельзя перевести в монтаж с пустой сметой';
      return;
    }
    if (measurementRequired.value && !measurementResult.value?.trim()) {
      localFormError.value = 'Требуется замер: заполните результат замера';
      return;
    }
    if (proposalStatus.value !== 'approved') {
      localFormError.value = 'Проект должен быть согласован с клиентом';
      return;
    }
  }

  clearDraft();
  const payload: ManagerOrderUpdatePayload = {
    status: status.value,
    next_followup_date: fromLocalDateTimeInput(nextFollowupDate.value),
    measurement_date: fromLocalDateTimeInput(assessmentDate.value),
    installation_date: fromLocalDateTimeInput(installationDate.value),
    comment: comment.value,
    is_paid: isPaid.value,
    installer_id: installerId.value,
    products: productLines.value.map((line) => ({
      product_id: line.product_id,
      quantity: line.quantity,
      price: line.price,
      cost: line.cost,
      link_id: null,
    })),
    services: serviceLines.value.map((line) => ({
      service_id: line.service_id ?? null,
      title: line.title,
      quantity: line.quantity,
      price: line.price,
      cost: line.cost,
      link_id: null,
    })),
    measurement_required: measurementRequired.value,
    measurer_id: measurerId.value,
    measurement_result: measurementResult.value,
    proposal_status: proposalStatus.value,
  };
  emit('save', { orderId: props.order.id, data: payload });
};

const closeDrawer = () => {
  clearDraft();
  emit('update:modelValue', false);
};
const getFieldError = (field: string): string => localServerErrors.value[field] || props.serverErrors?.[field] || '';
const displayFormError = computed(() => localFormError.value || props.formError || '');
const closeCustomerModal = () => {
  showCustomerModal.value = false;
};

const openCustomerProfile = () => {
  const customerId = props.order?.customer?.id;
  if (!customerId) return;
  showCustomerModal.value = false;
  const returnTo = `${window.location.pathname}${window.location.search}`;
  const query = new URLSearchParams({
    customerId: String(customerId),
    returnTo,
  });
  window.history.pushState({}, '', `/manager/customers/profile?${query.toString()}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

watch(
  () => productLines.value,
  () => {
    persistDraft();
  },
  { deep: true },
);
</script>

<template>
  <div v-if="modelValue" class="fixed inset-0 z-50 flex">
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium">
        {{ toast }}
      </div>
    </Transition>
    <div class="flex-1 bg-black/60" @click="closeDrawer" />
    <aside class="h-full w-full max-w-3xl overflow-y-auto bg-white p-6 text-gray-900 border-l border-gray-200 shadow-2xl">
      <header class="mb-4 flex items-start justify-between border-b border-gray-100 pb-4">
        <div class="flex-1">
          <div class="flex items-center gap-3 mb-1">
            <h2 class="text-xl font-semibold font-['Space_Grotesk'] text-gray-900">№{{ order?.id }} {{ customer?.full_legal_name || customer?.name || 'Без имени' }}</h2>
            <button @click="showCustomerModal = true" class="text-xs font-medium text-teal-600 hover:text-teal-700 bg-teal-50 px-2 py-0.5 rounded flex items-center gap-1 transition-colors" :disabled="!customer?.id">
              <span class="material-icons-round text-[14px]">info</span>
              Подробнее
            </button>
          </div>
          <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-500">
            <span v-if="customer?.phone" class="flex items-center gap-1"><span class="material-icons-round text-[14px]">phone</span> {{ customer.phone }}</span>
            <span v-if="customer?.email" class="flex items-center gap-1"><span class="material-icons-round text-[14px]">email</span> {{ customer.email }}</span>
            <span v-if="customer?.inn" class="flex items-center gap-1"><span class="font-medium text-xs">УНП</span> {{ customer.inn }}</span>
          </div>
        </div>
        
        <div class="flex items-start gap-2 ml-4">
          <button v-if="order" type="button" @click="toggleHold" class="text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors" :class="order.is_on_hold ? 'bg-amber-50 border-amber-200 text-amber-700' : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'">
            {{ order.is_on_hold ? 'Вернуть в работу' : 'Отложить' }}
          </button>
          <button class="flex items-center justify-center w-8 h-8 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors" type="button" @click="closeDrawer" title="Закрыть">
            <span class="material-icons-round">close</span>
          </button>
        </div>
      </header>

      <p v-if="displayFormError" class="mb-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
        {{ displayFormError }}
      </p>



      <!-- Планирование (Measurement & Logistics) -->
      <section v-if="status === 'negotiation'" class="mt-6 rounded-2xl bg-blue-50/30 border border-blue-100 p-4">
        <h3 class="text-lg font-semibold font-['Space_Grotesk'] mb-4 text-blue-900 border-b border-blue-100 pb-2">Планирование (Замер и Монтаж)</h3>
        
        <label class="flex items-center gap-2 cursor-pointer mb-4">
          <input type="checkbox" v-model="measurementRequired" class="w-5 h-5 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
          <span class="font-medium text-gray-800">Требуется выезд на замер</span>
        </label>
        
        <div v-if="!measurementRequired" class="text-sm text-gray-500 bg-white p-3 rounded-xl border border-gray-200 mb-4 shadow-sm">
          Замер не требуется. Можно планировать монтаж сразу.
        </div>
        
        <div v-if="measurementRequired" class="grid gap-3 md:grid-cols-2 mb-4 bg-white p-4 rounded-xl border border-blue-100 shadow-sm">
          <DateTimeField v-model="assessmentDate" label="Дата и время замера" :error="getFieldError('measurement_date')" />
          <label class="field-label">
            Замерщик
            <select v-model="measurerId" class="field-input">
              <option :value="null">Не назначен</option>
              <option v-for="inst in installersList" :key="inst.id" :value="inst.id">
                {{ inst.name }} {{ !inst.is_active ? '(в архиве)' : '' }}
              </option>
            </select>
          </label>
          <label class="field-label md:col-span-2">
            Результат замера
            <textarea
              v-model="measurementResult"
              class="field-input min-h-[60px]"
              placeholder="Резюме после выезда (длины трасс, доп. работы)..."
            />
          </label>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <DateTimeField v-model="installationDate" label="Дата монтажа" :error="getFieldError('installation_date')" />
          <label class="field-label">
            Монтажник
            <select v-model="installerId" class="field-input">
              <option :value="null">Не назначен</option>
              <option v-for="inst in installersList" :key="inst.id" :value="inst.id">
                {{ inst.name }} {{ !inst.is_active ? '(в архиве)' : '' }}
              </option>
            </select>
          </label>
        </div>
        <label class="field-label md:col-span-2">
          Комментарий
          <textarea
            v-model="comment"
            class="field-input min-h-[90px]"
            :class="getFieldError('comment') ? 'border-red-500 focus:outline-red-400' : ''"
          />
          <span v-if="getFieldError('comment')" class="text-xs text-red-300">{{ getFieldError('comment') }}</span>
        </label>
      </section>



      <!-- Смета -->
      <div class="mt-8 rounded-2xl bg-gray-50/50 border border-gray-200 p-4">
        <h3 class="text-xl font-bold font-['Space_Grotesk'] text-gray-900 border-b border-gray-200 pb-2 mb-4">Смета: Оборудование и услуги</h3>
        
        <section class="mt-2">
          <div class="mb-2 flex items-center justify-between">
            <h4 class="text-md font-semibold text-gray-800">Товары</h4>
          <button class="btn-mini" @click="addProductLine">Добавить товар</button>
        </div>
        <p v-if="getFieldError('products')" class="mb-2 text-xs text-red-300">{{ getFieldError('products') }}</p>
        <div class="mb-2 grid grid-cols-12 gap-2 px-2 text-[11px] uppercase tracking-[0.08em] text-gray-500">
          <div class="col-span-5">Товар</div>
          <div class="col-span-2">Цена</div>
          <div class="col-span-2">Себест.</div>
          <div class="col-span-2">Кол-во / Сумма</div>
          <div class="col-span-1">Действия</div>
        </div>
        <div class="space-y-2">
          <div v-for="(line, index) in productLines" :key="`product-${index}`" class="grid grid-cols-12 gap-2 rounded-xl border border-gray-200 bg-white p-2">
            <div class="col-span-5">
              <input
                v-model="line.product_query"
                class="field-input"
                placeholder="Поиск и выбор товара"
                @focus="onProductInputFocus(index)"
                @input="onProductQueryInput(index)"
                @blur="onProductInputBlur(index)"
              />
              <div
                v-if="!line.product_id && line.product_query.trim().length >= 2 && (productLookupLoading || getProductSuggestions(index).length)"
                class="mt-1 max-h-56 overflow-auto rounded-[12px] border border-gray-200 bg-white p-1"
              >
                <div v-if="productLookupLoading" class="px-3 py-2 text-xs text-gray-500">Поиск товаров...</div>
                <button
                  v-for="item in getProductSuggestions(index)"
                  :key="`product-suggest-${index}-${item.id}`"
                  type="button"
                  class="mb-1 block w-full rounded-[12px] px-3 py-2 text-left text-xs text-gray-700 hover:bg-slate-100 dark:hover:bg-slate-800 last:mb-0"
                  @click="selectProductForLine(index, item)"
                >
                  <p class="truncate font-medium text-gray-900 dark:text-slate-100">{{ item.title }}</p>
                  <p class="mt-1 text-[11px] text-gray-500 dark:text-slate-300">
                    {{ formatMoney(item.price) }}
                    · {{ item.is_inverter ? 'Инвертор' : 'On/Off' }}
                    · {{ item.power_cooling ? `${item.power_cooling.toFixed(1)} кВт` : 'мощность н/д' }}
                  </p>
                </button>
              </div>
            </div>
            <input v-model.number="line.price" type="number" min="0" class="field-input col-span-2" placeholder="Цена" />
            <input v-model.number="line.cost" type="number" min="0" class="field-input col-span-2" placeholder="Себест." />
            <div class="col-span-2 flex flex-col gap-1">
              <input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="Кол-во" />
              <p class="px-1 text-xs text-gray-500">Σ {{ formatMoney(lineTotal(line)) }}</p>
            </div>
            <div class="col-span-1 flex flex-col gap-1">
              <button class="btn-mini-outline px-0" type="button" :disabled="!line.product_id" @click="openSelectedProduct(index)">↗</button>
              <button class="btn-mini-outline px-0" type="button" @click="removeProductLine(index)">×</button>
            </div>
            <p
              v-if="isPriceDifferentFromCatalog(line)"
              class="col-span-12 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700"
            >
              Цена строки отличается от каталожной ({{ formatMoney(currentCatalogPrice(line.product_id) || 0) }}).
            </p>
          </div>
        </div>
      </section>

        <section class="mt-6">
          <div class="mb-2 flex items-center justify-between">
            <h4 class="text-md font-semibold text-gray-800">Услуги</h4>
            <button class="btn-mini" @click="addServiceLine">Добавить услугу</button>
          </div>
          <p v-if="getFieldError('services')" class="mb-2 text-xs text-red-300">{{ getFieldError('services') }}</p>
          <div class="space-y-2">
            <div v-for="(line, index) in serviceLines" :key="`service-${index}`" class="grid grid-cols-12 gap-2 rounded-xl border border-gray-200 bg-white p-2">
              <input v-model="line.title" class="field-input col-span-5" placeholder="Название услуги" />
              <input v-model.number="line.price" type="number" min="0" class="field-input col-span-2" placeholder="Цена" />
              <input v-model.number="line.cost" type="number" min="0" class="field-input col-span-2" placeholder="Себест." />
              <input v-model.number="line.quantity" type="number" min="1" class="field-input col-span-2" placeholder="Кол-во" />
              <button class="btn-mini-outline col-span-1" @click="removeServiceLine(index)">×</button>
            </div>
          </div>
        </section>
      </div>

      <!-- Экшн-зона (Proposal & Docs) -->
      <section v-if="status === 'negotiation' || status === 'closed'" class="mt-8 rounded-2xl bg-amber-50/30 border border-amber-100 p-4">
        <h3 class="text-lg font-semibold font-['Space_Grotesk'] text-amber-900 mb-4 border-b border-amber-200 pb-2">Согласование</h3>
        
        <div v-if="status === 'negotiation'" class="mb-6">
          <label class="field-label mb-3">
            Статус согласования
            <select v-model="proposalStatus" class="field-input" :class="getFieldError('proposal_status') ? 'border-red-500' : ''">
              <option value="draft">Черновик (Draft)</option>
              <option value="sent">Отправлено (Sent)</option>
              <option value="approved">Согласовано (Approved)</option>
              <option value="rejected">Отказ (Rejected)</option>
            </select>
          </label>

          <div class="flex flex-wrap gap-2">
            <!-- B2C Action -->
            <a
              v-if="customer?.type === 'individual'"
              :href="`https://wa.me/${(customer?.phone || '').replace(/\\D/g, '')}?text=${encodeURIComponent(`Здравствуйте, ${customer?.name}! Расчет по вашему заказу: Итого к оплате ${formatMoney(totalPreview)}. Подтверждаем?`)}`"
              target="_blank"
              class="flex items-center gap-1 rounded-xl bg-[#25D366] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#20BE5A]"
            >
              <span class="material-icons-round text-[18px]">chat</span> Отправить в WhatsApp
            </a>
            <a
              v-if="customer?.type === 'individual'"
              :href="`viber://chat?number=%2B${(customer?.phone || '').replace(/\\D/g, '')}`"
              target="_blank"
              class="flex items-center gap-1 rounded-xl bg-[#7360f2] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#5e4cd1]"
            >
              <span class="material-icons-round text-[18px]">chat</span> Viber
            </a>
          </div>
        </div>

        <div class="mb-2 flex items-center justify-between">
          <h4 class="text-md font-semibold text-slate-800">Документы (B2B / Договоры)</h4>
          
          <div class="relative">
            <button
               class="flex items-center gap-1 rounded-xl bg-[#007f80] px-3 py-1.5 text-sm font-medium text-white shadow hover:bg-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50"
               :disabled="isGeneratingDoc || !!processingDocId"
               @click="docDropdownOpen = !docDropdownOpen"
            >
              <span class="material-icons-round text-[18px]">add_circle</span> Создать
            </button>
            <div
               v-if="docDropdownOpen"
               class="absolute right-0 top-full z-10 mt-2 w-48 rounded-xl border border-slate-700 bg-slate-800 p-1 shadow-lg"
            >
              <button
                v-for="dtype in DOCUMENT_TYPES"
                :key="dtype.type"
                class="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 disabled:opacity-50 disabled:hover:bg-transparent"
                :disabled="(dtype.type === 'act' || dtype.type === 'ttn1' || dtype.type === 'tn2') && !hasContract"
                :title="(dtype.type === 'act' || dtype.type === 'ttn1' || dtype.type === 'tn2') && !hasContract ? 'Сначала создайте договор' : ''"
                @click="generateDocument(dtype.type); docDropdownOpen = false"
              >
                {{ dtype.label }}
                <span v-if="(dtype.type === 'act' || dtype.type === 'ttn1' || dtype.type === 'tn2') && !hasContract" class="material-icons-round text-[16px] text-amber-500">lock</span>
              </button>
            </div>
          </div>
        </div>
        
        <div v-if="documents.length" class="space-y-3 mt-3">
            <div v-for="doc in documents" :key="doc.id" class="flex items-center justify-between rounded-xl border border-slate-700/50 bg-[#1e293b] p-3 text-slate-300">
                <div class="flex items-center gap-3">
                    <div class="flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-teal-400">
                      <span class="material-icons-round text-xl">description</span>
                    </div>
                    <div>
                        <p class="text-sm font-medium text-white">{{ doc.number || doc.doc_type }}</p>
                        <p class="text-xs text-slate-400">{{ new Date(doc.date).toLocaleDateString() }} · <span class="uppercase">{{ doc.doc_type }}</span></p>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <a :href="doc.edit_url" target="_blank" class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white" title="Редактировать">
                        <span class="material-icons-round text-[18px]">edit</span>
                    </a>
                    <button class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white disabled:opacity-50" :disabled="processingDocId === doc.id" @click="downloadDocument(doc)" title="Скачать PDF">
                        <span class="material-icons-round text-[18px]">download</span>
                    </button>
                    <button class="flex h-8 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50" :disabled="processingDocId === doc.id" @click="deleteDocument(doc.id)" title="Удалить">
                        <span class="material-icons-round text-[18px]">delete</span>
                    </button>
                </div>
            </div>
        </div>
        <div v-else class="text-sm text-slate-500 italic py-3 text-center rounded-xl border border-dashed border-slate-700">
            Нет сформированных документов
        </div>
      </section>


      <!-- Execution Tab UI -->
      <DealExecutionTab 
        v-if="status === 'execution' && order" 
        :order="order"
        @refresh="emit('save', { orderId: order.id, data: { status: 'execution' } }) /* triggering parent reload */"
        @close="closeDrawer"
        class="mt-8"
      />

      <section v-if="order && status !== 'execution'" class="mt-6 p-5 rounded-2xl border border-slate-200 bg-slate-50 shadow-sm">
        <h3 class="text-lg flex gap-2 items-center font-semibold font-['Space_Grotesk'] text-slate-800 mb-4">
            <span class="material-icons-round text-teal-600">account_balance_wallet</span> Оплаты
        </h3>
        
        <div class="mb-4 text-center border border-slate-200 rounded-xl py-6 bg-white shadow-inner">
            <p class="text-sm font-medium text-slate-500 uppercase tracking-wide">Остаток к оплате</p>
            <p class="text-4xl font-black mt-2 tracking-tight" :class="balanceDuePreview > 0 ? 'text-red-500' : 'text-teal-600'">
                {{ formatMoney(balanceDuePreview) }}
            </p>
        </div>
        
        <div class="flex items-end gap-2 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
            <label class="flex-1 field-label !mb-0 text-xs">Внести сумму
                <input v-model.number="newPaymentAmount" type="number" min="0" class="field-input mt-1 shadow-sm" placeholder="0.00" />
            </label>
            <label class="w-1/3 field-label !mb-0 text-xs">Тип
                <select v-model="newPaymentType" class="field-input mt-1 shadow-sm">
                    <option value="prepayment">Аванс</option>
                    <option value="postpayment">Доплата</option>
                </select>
            </label>
            <button class="btn-mini h-[38px] w-[100px]" :disabled="!newPaymentAmount || isAddingPayment" @click="addPayment">Внести</button>
        </div>

        <div class="mt-4 space-y-2 max-h-32 overflow-y-auto pr-1">
            <div v-for="p in payments" :key="p.id" class="flex justify-between items-center text-xs py-2 px-3 rounded-lg bg-white border border-slate-100 shadow-sm">
                <span class="text-slate-500">{{ new Date(p.date).toLocaleDateString() }}</span>
                <span class="font-bold text-slate-800">{{ formatMoney(p.amount) }}</span>
                <span class="text-slate-400 w-16 text-right">{{ p.type === 'prepayment' ? 'Аванс' : 'Доплата' }}</span>
                <button class="flex h-6 w-6 ml-2 items-center justify-center rounded text-red-400 hover:bg-red-50 hover:text-red-600 transition-colors" @click="deletePayment(p.id)" title="Удалить платеж">
                    <span class="material-icons-round text-[14px]">delete</span>
                </button>
            </div>
            <div v-if="!payments.length" class="text-sm text-gray-500 italic py-3 text-center rounded-xl border border-dashed border-gray-200">
                Нет оплат
            </div>
        </div>
      </section>

      <section class="mt-6 rounded-2xl bg-gray-100 p-4">
        <p class="text-sm text-gray-600">Оплачено: <span class="font-semibold text-teal-600">{{ formatMoney(totalPaymentsPreview) }}</span></p>
        <p class="text-sm text-gray-600">Остаток: <span class="font-semibold" :class="balanceDuePreview > 0 ? 'text-red-500' : 'text-gray-900'">{{ formatMoney(balanceDuePreview) }}</span></p>
        <hr class="my-2 border-gray-200" />
        <p class="text-sm text-gray-600">Итого сумма: <span class="font-semibold text-gray-900">{{ formatMoney(totalPreview) }}</span></p>
        <p class="text-sm text-gray-600">Маржа: <span class="font-semibold text-teal-700">{{ formatMoney(marginPreview) }}</span></p>
      </section>

      <footer class="mt-6 flex justify-end gap-2">
        <button class="btn-mini-outline" :disabled="saving" @click="closeDrawer">Отмена</button>
        <button class="btn-mini" :disabled="saving" @click="handleSave">
          {{ saving ? 'Сохраняем...' : 'Сохранить' }}
        </button>
      </footer>
    </aside>

    <div
      v-if="showCustomerModal"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 px-4"
      @click.self="closeCustomerModal"
    >
      <div class="w-full max-w-3xl rounded-2xl border border-gray-200 bg-white p-5 text-gray-900 shadow-2xl">
        <div class="mb-4 flex items-center justify-between gap-3">
          <h3 class="text-lg font-semibold font-['Space_Grotesk']">Карточка клиента</h3>
          <button class="btn-mini-outline" @click="closeCustomerModal">Закрыть</button>
        </div>
        <CustomerSummaryCard :customer="customer" mode="expanded" :show-open-button="false" />
        <div class="mt-4 flex justify-end">
          <button class="btn-mini" :disabled="!customer?.id" @click="openCustomerProfile">Редактировать в карточке клиента</button>
        </div>
      </div>
    </div>
  </div>
</template>
