<script setup lang="ts">
import { computed, ref, watch } from 'vue';
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

type ProductOption = { id: number; text: string; price: number };
type ProductLine = { product_id: number; product_query: string; quantity: number; price: number; cost: number };
type ServiceLine = { service_id?: number | null; title: string; quantity: number; price: number; cost: number };

type OrderDrawerDraft = {
  productLines: ProductLine[];
};

const productOptions = ref<ProductOption[]>([]);
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

const loadProductOptions = async (q = '') => {
  const response = await api.searchProducts(q);
  productOptions.value = (response || []).map((item: { id: number; text: string; price: number }) => ({
    id: item.id,
    text: item.text,
    price: item.price,
  }));
};

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

  await loadProductOptions('');
  restoreDraft();
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
  const selected = productOptions.value.find((item) => item.id === row.product_id);
  if (!selected) return;
  row.product_query = selected.text;
  if (applyCatalogPrice) {
    row.price = selected.price;
  }
};

const getProductSuggestions = (query: string, currentProductId = 0) => {
  const normalized = query.trim().toLowerCase();
  const filtered = normalized
    ? productOptions.value.filter((item) => item.text.toLowerCase().includes(normalized))
    : productOptions.value;
  if (currentProductId && !filtered.some((item) => item.id === currentProductId)) {
    const current = productOptions.value.find((item) => item.id === currentProductId);
    if (current) return [current, ...filtered].slice(0, 10);
  }
  return filtered.slice(0, 10);
};

const onProductQueryInput = async (index: number) => {
  const row = productLines.value[index];
  if (!row) return;
  const query = row.product_query.trim();
  row.product_id = 0;
  if (query.length < 2) return;
  await loadProductOptions(query);
};

const selectProductForLine = (index: number, option: ProductOption) => {
  const row = productLines.value[index];
  if (!row) return;
  const isNewLine = !row.product_id && Number(row.price || 0) <= 0;
  row.product_id = option.id;
  row.product_query = option.text;
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

const currentCatalogPrice = (productId: number) => productOptions.value.find((item) => item.id === productId)?.price ?? null;
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
    <div class="flex-1 bg-black/60" @click="closeDrawer" />
    <aside class="h-full w-full max-w-3xl overflow-y-auto bg-white p-6 text-gray-900 border-l border-gray-200 shadow-2xl">
      <header class="mb-4 flex items-center justify-between">
        <h2 class="text-xl font-semibold">Редактирование заказа #{{ order?.id }}</h2>
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
          <h3 class="text-lg font-semibold">Клиент</h3>
          <div class="flex flex-wrap gap-2">
            <button class="btn-mini-outline" :disabled="!customer?.id" @click="showCustomerModal = true">Подробнее</button>
            <button class="btn-mini-outline" :disabled="!customer?.id" @click="openCustomerProfile">Открыть карточку</button>
          </div>
        </div>
        <CustomerSummaryCard :customer="customer" mode="compact" :show-open-button="false" />
      </section>

      <section class="mt-6">
        <div class="mb-2 flex items-center justify-between">
          <h3 class="text-lg font-semibold">Товары</h3>
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
                @input="onProductQueryInput(index)"
              />
              <div
                v-if="!line.product_id && line.product_query.trim().length >= 2 && getProductSuggestions(line.product_query).length"
                class="mt-1 max-h-44 overflow-auto rounded-lg border border-gray-200 bg-white p-1"
              >
                <button
                  v-for="item in getProductSuggestions(line.product_query)"
                  :key="`product-suggest-${index}-${item.id}`"
                  type="button"
                  class="block w-full rounded px-2 py-1 text-left text-xs text-gray-700 hover:bg-gray-100"
                  @click="selectProductForLine(index, item)"
                >
                  {{ item.text }}
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
          <h3 class="text-lg font-semibold">Услуги</h3>
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
          <h3 class="text-lg font-semibold">Карточка клиента</h3>
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
