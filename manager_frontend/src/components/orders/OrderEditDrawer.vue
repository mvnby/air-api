<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
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
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  save: [payload: { orderId: number; data: ManagerOrderUpdatePayload }];
}>();

type ProductOption = { id: number; text: string; price: number };

const productOptions = ref<ProductOption[]>([]);
const productSearch = ref('');
const status = ref('new_lead');
const nextFollowupDate = ref('');
const assessmentDate = ref('');
const installationDate = ref('');
const comment = ref('');
const isPaid = ref(false);

const productLines = ref<Array<{ product_id: number; quantity: number; price: number; cost: number }>>([]);
const serviceLines = ref<Array<{ service_id?: number | null; title: string; quantity: number; price: number; cost: number }>>([]);

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

const initForm = async (order: ManagerOrderDetailResponse | null) => {
  if (!order) return;
  status.value = order.status;
  nextFollowupDate.value = toLocalDateTimeInput(order.next_followup_date);
  assessmentDate.value = toLocalDateTimeInput(order.assessment_date);
  installationDate.value = toLocalDateTimeInput(order.installation_date);
  comment.value = order.comment ?? '';
  isPaid.value = order.is_paid;
  productLines.value = (order.product_lines ?? []).map((line: OrderProductLineResponse) => ({
    product_id: line.product_id || 0,
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

watch(productSearch, async (value) => {
  await loadProductOptions(value);
});

const onProductChanged = (index: number) => {
  const row = productLines.value[index];
  if (!row) return;
  const selected = productOptions.value.find((item) => item.id === row.product_id);
  if (!selected) return;
  const shouldUseCatalog = window.confirm(
    `Для товара \"${selected.text}\" использовать текущую цену каталога ${selected.price}?\nНажмите OK для каталожной цены или Отмена, чтобы оставить цену строки.`,
  );
  if (shouldUseCatalog) {
    row.price = selected.price;
  }
};

const addProductLine = () => {
  productLines.value.push({ product_id: 0, quantity: 1, price: 0, cost: 0 });
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

const handleSave = () => {
  if (!props.order) return;
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

const closeDrawer = () => emit('update:modelValue', false);

const getFieldError = (field: string): string => props.serverErrors?.[field] || '';
</script>

<template>
  <div v-if="modelValue" class="fixed inset-0 z-50 flex">
    <div class="flex-1 bg-black/60" @click="closeDrawer" />
    <aside class="h-full w-full max-w-3xl overflow-y-auto bg-slate-900 p-6 text-slate-100 shadow-2xl">
      <header class="mb-4 flex items-center justify-between">
        <h2 class="text-xl font-semibold">Редактирование заказа #{{ order?.id }}</h2>
        <button class="btn-mini-outline" @click="closeDrawer">Закрыть</button>
      </header>

      <p v-if="formError" class="mb-4 rounded-xl border border-red-500/40 bg-red-900/30 px-3 py-2 text-sm text-red-200">
        {{ formError }}
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

      <section class="mt-6">
        <div class="mb-2 flex items-center justify-between">
          <h3 class="text-lg font-semibold">Товары</h3>
          <button class="btn-mini" @click="addProductLine">Добавить товар</button>
        </div>
        <p v-if="getFieldError('products')" class="mb-2 text-xs text-red-300">{{ getFieldError('products') }}</p>
        <label class="field-label mb-2">
          Поиск товара
          <input v-model="productSearch" class="field-input" placeholder="Введите название товара" />
        </label>
        <div class="space-y-2">
          <div v-for="(line, index) in productLines" :key="`product-${index}`" class="grid grid-cols-12 gap-2 rounded-xl bg-slate-800 p-2">
            <select v-model.number="line.product_id" class="field-input col-span-5" @change="onProductChanged(index)">
              <option :value="0">Выберите товар</option>
              <option v-for="item in productOptions" :key="item.id" :value="item.id">{{ item.text }}</option>
            </select>
            <input v-model.number="line.price" type="number" min="0" class="field-input col-span-2" placeholder="Цена" />
            <input v-model.number="line.cost" type="number" min="0" class="field-input col-span-2" placeholder="Себест." />
            <input v-model.number="line.quantity" type="number" min="1" class="field-input col-span-2" placeholder="Кол-во" />
            <button class="btn-mini-outline col-span-1" @click="removeProductLine(index)">×</button>
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
          <div v-for="(line, index) in serviceLines" :key="`service-${index}`" class="grid grid-cols-12 gap-2 rounded-xl bg-slate-800 p-2">
            <input v-model="line.title" class="field-input col-span-5" placeholder="Название услуги" />
            <input v-model.number="line.price" type="number" min="0" class="field-input col-span-2" placeholder="Цена" />
            <input v-model.number="line.cost" type="number" min="0" class="field-input col-span-2" placeholder="Себест." />
            <input v-model.number="line.quantity" type="number" min="1" class="field-input col-span-2" placeholder="Кол-во" />
            <button class="btn-mini-outline col-span-1" @click="removeServiceLine(index)">×</button>
          </div>
        </div>
      </section>

      <section class="mt-6 rounded-2xl bg-slate-800 p-4">
        <p class="text-sm text-slate-300">Итого: <span class="font-semibold text-white">{{ formatMoney(totalPreview) }}</span></p>
        <p class="text-sm text-slate-300">Маржа: <span class="font-semibold text-teal-300">{{ formatMoney(marginPreview) }}</span></p>
      </section>

      <footer class="mt-6 flex justify-end gap-2">
        <button class="btn-mini-outline" @click="closeDrawer">Отмена</button>
        <button class="btn-mini" @click="handleSave">Сохранить</button>
      </footer>
    </aside>
  </div>
</template>
