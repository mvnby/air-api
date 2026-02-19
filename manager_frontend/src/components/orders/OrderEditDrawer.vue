<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
import CustomerSummaryCard from '../customers/CustomerSummaryCard.vue';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
  OrderProductLineResponse,
  OrderServiceLineResponse,
} from '../../client';
import { STATUS_LABELS, STATUS_ORDER, formatMoney } from './order-utils';
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

const productLines = ref<ProductLine[]>([]);
const serviceLines = ref<ServiceLine[]>([]);
const localServerErrors = ref<Record<string, string>>({});
const localFormError = ref('');
const showCustomerModal = ref(false);

const customer = computed(() => props.order?.customer ?? null);
const draftKey = computed(() => (props.order ? `manager_order_drawer_draft_${props.order.id}` : ''));

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const totalPreview = computed(() => {
  const pTotal = productLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
  const sTotal = serviceLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
  return pTotal + sTotal;
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
  assessmentDate.value = toLocalDateTimeInput(order.assessment_date);
  installationDate.value = toLocalDateTimeInput(order.installation_date);
  comment.value = order.comment ?? '';
  isPaid.value = order.is_paid;
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

  clearDraft();
  const payload: ManagerOrderUpdatePayload = {
    status: status.value,
    next_followup_date: fromLocalDateTimeInput(nextFollowupDate.value),
    assessment_date: fromLocalDateTimeInput(assessmentDate.value),
    installation_date: fromLocalDateTimeInput(installationDate.value),
    comment: comment.value,
    is_paid: isPaid.value,
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
      <header class="mb-4 flex items-center justify-between">
        <h2 class="text-xl font-semibold font-['Space_Grotesk']">Редактирование заказа #{{ order?.id }}</h2>
        <button class="btn-mini-outline" @click="closeDrawer">Закрыть</button>
      </header>

      <p v-if="displayFormError" class="mb-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
        {{ displayFormError }}
      </p>

      <section class="grid gap-3 md:grid-cols-2">
        <label class="field-label">
          Статус
          <select v-model="status" class="field-input" :class="getFieldError('status') ? 'border-red-500 focus:outline-red-400' : ''">
            <option v-for="statusKey in STATUS_ORDER" :key="statusKey" :value="statusKey">
              {{ STATUS_LABELS[statusKey] || statusKey }}
            </option>
          </select>
          <span v-if="getFieldError('status')" class="text-xs text-red-300">{{ getFieldError('status') }}</span>
        </label>
        <label class="field-label">
          Оплата
          <select v-model="isPaid" class="field-input" :class="getFieldError('is_paid') ? 'border-red-500 focus:outline-red-400' : ''">
            <option :value="false">Ожидает оплаты</option>
            <option :value="true">Оплачен</option>
          </select>
          <span v-if="getFieldError('is_paid')" class="text-xs text-red-300">{{ getFieldError('is_paid') }}</span>
        </label>
        <DateTimeField v-model="nextFollowupDate" label="Следующее касание" :error="getFieldError('next_followup_date')" />
        <DateTimeField v-model="assessmentDate" label="Дата замера" :error="getFieldError('assessment_date')" />
        <DateTimeField
          v-model="installationDate"
          class="md:col-span-2"
          label="Дата монтажа"
          :error="getFieldError('installation_date')"
        />
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

      <section class="mt-6 rounded-2xl bg-gray-100 p-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <h3 class="text-lg font-semibold font-['Space_Grotesk']">Клиент</h3>
          <div class="flex flex-wrap gap-2">
            <button class="btn-mini-outline" :disabled="!customer?.id" @click="showCustomerModal = true">Подробнее</button>
            <button class="btn-mini-outline" :disabled="!customer?.id" @click="openCustomerProfile">Открыть карточку</button>
          </div>
        </div>
        <CustomerSummaryCard :customer="customer" mode="compact" :show-open-button="false" />
      </section>

      <section class="mt-6">
        <div class="mb-2 flex items-center justify-between">
          <h3 class="text-lg font-semibold font-['Space_Grotesk']">Товары</h3>
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
          <h3 class="text-lg font-semibold font-['Space_Grotesk']">Услуги</h3>
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

      <section class="mt-6 rounded-2xl bg-gray-100 p-4">
        <p class="text-sm text-gray-600">Итого: <span class="font-semibold text-gray-900">{{ formatMoney(totalPreview) }}</span></p>
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
