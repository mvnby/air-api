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
import { useBelarusPhoneMask } from '../../composables/useBelarusPhoneMask';
import { STATUS_LABELS, STATUS_ORDER, formatMoney } from './order-utils';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../../utils/datetime';
import { normalizeIban, normalizeUnp } from '../../utils/legal-requisites';
import { normalizePhoneForApi } from '../../utils/phone';
import { normalizeEmail, validateOptionalBelarusPhone, validateOptionalByIban, validateOptionalByUnp, validateOptionalEmail } from '../../utils/validation';

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

const productOptions = ref<ProductOption[]>([]);
const productSearch = ref('');
const status = ref('new_lead');
const nextFollowupDate = ref('');
const assessmentDate = ref('');
const installationDate = ref('');
const comment = ref('');
const isPaid = ref(false);
const customerName = ref('');
const customerPhone = ref('');
const customerEmail = ref('');
const customerInn = ref('');
const customerFullLegalName = ref('');
const customerLegalAddress = ref('');
const customerBankName = ref('');
const customerBic = ref('');
const customerIban = ref('');
const customerDeliveryAddress = ref('');
const showCriticalConfirmPanel = ref(false);
const criticalChangesConfirmed = ref(false);
const customerOriginalCritical = ref<{ inn: string; bic: string; iban: string; bank_name: string } | null>(null);
const customerPhoneInputRef = ref<HTMLInputElement | null>(null);
const customerPhoneError = ref('');
const customerEmailError = ref('');
const customerInnError = ref('');
const customerIbanError = ref('');

const productLines = ref<Array<{ product_id: number; quantity: number; price: number; cost: number }>>([]);
const serviceLines = ref<Array<{ service_id?: number | null; title: string; quantity: number; price: number; cost: number }>>([]);
const localServerErrors = ref<Record<string, string>>({});
const localFormError = ref('');
const customerPhoneModel = computed({
  get: () => customerPhone.value,
  set: (value: string) => {
    customerPhone.value = value;
  },
});
const customerPhoneMask = useBelarusPhoneMask(customerPhoneInputRef, customerPhoneModel);

const normalizeComparable = (value: string) => value.trim().replace(/\s+/g, ' ');

const criticalChangedRows = computed<Array<{ key: 'inn' | 'iban' | 'bic' | 'bank_name'; label: string; before: string; after: string }>>(() => {
  const original = customerOriginalCritical.value;
  if (!original) return [];
  const rows: Array<{ key: 'inn' | 'iban' | 'bic' | 'bank_name'; label: string; before: string; after: string }> = [];
  const checks: Array<{ key: 'inn' | 'iban' | 'bic' | 'bank_name'; label: string; before: string; after: string }> = [
    { key: 'inn', label: 'УНП', before: original.inn, after: customerInn.value },
    { key: 'iban', label: 'IBAN', before: original.iban, after: customerIban.value },
    { key: 'bic', label: 'BIC', before: original.bic, after: customerBic.value },
    { key: 'bank_name', label: 'Банк', before: original.bank_name, after: customerBankName.value },
  ];
  for (const row of checks) {
    const beforeNorm = normalizeComparable(row.before);
    const afterNorm = normalizeComparable(row.after);
    if (beforeNorm && afterNorm && beforeNorm !== afterNorm) {
      rows.push({
        key: row.key,
        label: row.label,
        before: row.before.trim() || '—',
        after: row.after.trim() || '—',
      });
    }
  }
  return rows;
});

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
  localServerErrors.value = {};
  localFormError.value = '';
  customerPhoneError.value = '';
  customerEmailError.value = '';
  customerInnError.value = '';
  customerIbanError.value = '';
  showCriticalConfirmPanel.value = false;
  criticalChangesConfirmed.value = false;
  status.value = order.status;
  nextFollowupDate.value = toLocalDateTimeInput(order.next_followup_date);
  assessmentDate.value = toLocalDateTimeInput(order.assessment_date);
  installationDate.value = toLocalDateTimeInput(order.installation_date);
  comment.value = order.comment ?? '';
  isPaid.value = order.is_paid;
  customerName.value = order.customer?.name || '';
  customerPhone.value = order.customer?.phone || '';
  customerEmail.value = order.customer?.email || '';
  customerInn.value = order.customer?.inn || '';
  customerFullLegalName.value = order.customer?.full_legal_name || '';
  customerLegalAddress.value = order.customer?.legal_address || '';
  customerBankName.value = order.customer?.bank_name || '';
  customerBic.value = order.customer?.bic || '';
  customerIban.value = order.customer?.iban || '';
  customerDeliveryAddress.value = order.delivery_address || '';
  customerOriginalCritical.value = {
    inn: order.customer?.inn || '',
    bic: order.customer?.bic || '',
    iban: order.customer?.iban || '',
    bank_name: order.customer?.bank_name || '',
  };
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
  localServerErrors.value = {};
  localFormError.value = '';
  customerEmail.value = normalizeEmail(customerEmail.value || '');
  customerInn.value = normalizeUnp(customerInn.value || '');
  customerIban.value = normalizeIban(customerIban.value || '');
  customerPhoneError.value = validateOptionalBelarusPhone(customerPhone.value || '', customerPhoneMask.isComplete.value);
  customerEmailError.value = validateOptionalEmail(customerEmail.value || '');
  customerInnError.value = validateOptionalByUnp(customerInn.value || '');
  customerIbanError.value = validateOptionalByIban(customerIban.value || '');

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
  if (customerPhoneError.value) {
    errors.customer_phone = customerPhoneError.value;
  }
  if (customerEmailError.value) {
    errors.customer_email = customerEmailError.value;
  }
  if (customerInnError.value) {
    errors.customer_inn = customerInnError.value;
  }
  if (customerIbanError.value) {
    errors.customer_iban = customerIbanError.value;
  }

  if (Object.keys(errors).length) {
    localServerErrors.value = errors;
    localFormError.value = 'Исправьте ошибки в форме';
    return;
  }
  if (criticalChangedRows.value.length && !criticalChangesConfirmed.value) {
    showCriticalConfirmPanel.value = true;
    return;
  }
  showCriticalConfirmPanel.value = false;
  const payload: ManagerOrderUpdatePayload = {
    status: status.value,
    next_followup_date: fromLocalDateTimeInput(nextFollowupDate.value),
    assessment_date: fromLocalDateTimeInput(assessmentDate.value),
    installation_date: fromLocalDateTimeInput(installationDate.value),
    comment: comment.value,
    is_paid: isPaid.value,
    customer_name: customerName.value || null,
    customer_phone: normalizePhoneForApi(customerPhone.value || '') || null,
    customer_email: customerEmail.value || null,
    customer_inn: customerInn.value || null,
    customer_full_legal_name: customerFullLegalName.value || null,
    customer_legal_address: customerLegalAddress.value || null,
    customer_bank_name: customerBankName.value || null,
    customer_bic: customerBic.value || null,
    customer_iban: customerIban.value || null,
    customer_delivery_address: customerDeliveryAddress.value || null,
    confirm_critical_customer_changes: criticalChangesConfirmed.value,
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
const getFieldError = (field: string): string => localServerErrors.value[field] || props.serverErrors?.[field] || '';
const displayFormError = computed(() => localFormError.value || props.formError || '');
const confirmCriticalAndSave = () => {
  criticalChangesConfirmed.value = true;
  handleSave();
};

watch(
  () => `${customerInn.value}|${customerBic.value}|${customerIban.value}|${customerBankName.value}`,
  () => {
    criticalChangesConfirmed.value = false;
  },
);
</script>

<template>
  <div v-if="modelValue" class="fixed inset-0 z-50 flex">
    <div class="flex-1 bg-black/60" @click="closeDrawer" />
    <aside class="h-full w-full max-w-3xl overflow-y-auto bg-slate-900 p-6 text-slate-100 shadow-2xl">
      <header class="mb-4 flex items-center justify-between">
        <h2 class="text-xl font-semibold">Редактирование заказа #{{ order?.id }}</h2>
        <button class="btn-mini-outline" @click="closeDrawer">Закрыть</button>
      </header>

      <p v-if="displayFormError" class="mb-4 rounded-xl border border-red-500/40 bg-red-900/30 px-3 py-2 text-sm text-red-200">
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

      <section class="mt-6 rounded-2xl bg-slate-800/80 p-4">
        <h3 class="mb-3 text-lg font-semibold">Клиент</h3>
        <div class="grid gap-3 md:grid-cols-2">
          <label class="field-label">
            Имя / Компания
            <input
              v-model="customerName"
              class="field-input"
              :class="getFieldError('customer_name') ? 'border-red-500 focus:outline-red-400' : ''"
            />
            <span v-if="getFieldError('customer_name')" class="text-xs text-red-300">{{ getFieldError('customer_name') }}</span>
          </label>
          <label class="field-label">
            Телефон
            <input
              ref="customerPhoneInputRef"
              v-model="customerPhone"
              class="field-input"
              type="tel"
              inputmode="tel"
              placeholder="+375 (XX) XXX-XX-XX"
              :class="getFieldError('customer_phone') ? 'border-red-500 focus:outline-red-400' : ''"
            />
            <span v-if="getFieldError('customer_phone')" class="text-xs text-red-300">{{ getFieldError('customer_phone') }}</span>
          </label>
          <label class="field-label">
            Email
            <input
              v-model="customerEmail"
              class="field-input"
              type="email"
              :class="getFieldError('customer_email') ? 'border-red-500 focus:outline-red-400' : ''"
            />
            <span v-if="getFieldError('customer_email')" class="text-xs text-red-300">{{ getFieldError('customer_email') }}</span>
          </label>
          <label class="field-label">
            УНП
            <input
              v-model="customerInn"
              class="field-input"
              inputmode="numeric"
              :class="getFieldError('customer_inn') ? 'border-red-500 focus:outline-red-400' : ''"
            />
            <span v-if="getFieldError('customer_inn')" class="text-xs text-red-300">{{ getFieldError('customer_inn') }}</span>
          </label>
          <label class="field-label md:col-span-2">
            Полное наименование
            <input v-model="customerFullLegalName" class="field-input" />
          </label>
          <label class="field-label md:col-span-2">
            Юридический адрес
            <input v-model="customerLegalAddress" class="field-input" />
          </label>
          <label class="field-label">
            BIC
            <input v-model="customerBic" class="field-input" />
          </label>
          <label class="field-label">
            IBAN
            <input
              v-model="customerIban"
              class="field-input"
              :class="getFieldError('customer_iban') ? 'border-red-500 focus:outline-red-400' : ''"
            />
            <span v-if="getFieldError('customer_iban')" class="text-xs text-red-300">{{ getFieldError('customer_iban') }}</span>
          </label>
          <label class="field-label md:col-span-2">
            Банк
            <input v-model="customerBankName" class="field-input" />
          </label>
          <label class="field-label md:col-span-2">
            Адрес доставки
            <input v-model="customerDeliveryAddress" class="field-input" />
          </label>
        </div>
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

      <section
        v-if="showCriticalConfirmPanel && criticalChangedRows.length"
        class="mt-6 rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-100"
      >
        <p class="font-semibold text-red-50">Подтверждение изменения критичных реквизитов</p>
        <p class="mt-1 text-red-200/90">Будут обновлены реквизиты клиента:</p>
        <ul class="mt-2 list-inside list-disc space-y-1">
          <li v-for="row in criticalChangedRows" :key="`order-critical-${row.key}`">
            {{ row.label }}: {{ row.before }} -> {{ row.after }}
          </li>
        </ul>
        <div class="mt-3 flex flex-wrap gap-2">
          <button class="btn-mini bg-red-600/80 hover:bg-red-500" @click="confirmCriticalAndSave">Подтвердить и сохранить</button>
          <button class="btn-mini-outline" @click="showCriticalConfirmPanel = false">Отмена</button>
        </div>
      </section>

      <footer class="mt-6 flex justify-end gap-2">
        <button class="btn-mini-outline" :disabled="saving" @click="closeDrawer">Отмена</button>
        <button class="btn-mini" :disabled="saving" @click="handleSave">
          {{ saving ? 'Сохраняем...' : 'Сохранить' }}
        </button>
      </footer>
    </aside>
  </div>
</template>
