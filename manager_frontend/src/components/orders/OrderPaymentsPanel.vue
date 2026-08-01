<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type {
  BankReceiptResponse,
  FxRateResponse,
  ManagerOrderDetailResponse,
  PaymentCurrency,
  PaymentResponse,
} from '../../client';
import { ManagerMailService, ManagerOrdersService } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import OrderDrawerSection from './OrderDrawerSection.vue';
import { formatMoney } from './order-utils';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  expanded: boolean;
  payments: PaymentResponse[];
  enableCurrency: boolean;
  targetCurrency: PaymentCurrency | null;
  targetCurrencyAmount: number | null;
  currentFxRate: FxRateResponse | null;
  isB2cCustomer: boolean;
  total: number;
  totalPayments: number;
  balanceDue: number;
  margin: number;
  calculatedTargetCurrencyPayments: number;
  targetCurrencyBalanceDue: number;
}>();

const emit = defineEmits<{
  'update:expanded': [value: boolean];
  'update:payments': [value: PaymentResponse[]];
  'update:enableCurrency': [value: boolean];
  'update:targetCurrency': [value: PaymentCurrency | null];
  'update:targetCurrencyAmount': [value: number | null];
  toast: [payload: { message: string; type: 'success' | 'error' }];
  reload: [orderId: number];
}>();

const expandedModel = computed({
  get: () => props.expanded,
  set: (value: boolean) => emit('update:expanded', value),
});
const enableCurrencyModel = computed({
  get: () => props.enableCurrency,
  set: (value: boolean) => emit('update:enableCurrency', value),
});
const targetCurrencyModel = computed({
  get: () => props.targetCurrency,
  set: (value: PaymentCurrency | null) => emit('update:targetCurrency', value),
});
const targetCurrencyAmountModel = computed({
  get: () => props.targetCurrencyAmount,
  set: (value: number | null) => emit('update:targetCurrencyAmount', value),
});

const bankReceipts = ref<BankReceiptResponse[]>([]);
const bankReceiptsLoading = ref(false);
const attachingReceiptId = ref<number | null>(null);
const newPaymentAmount = ref<number | null>(null);
const newPaymentType = ref('prepayment');
const isAddingPayment = ref(false);
const deletingPaymentId = ref<number | null>(null);

const summary = computed(() => (
  `оплачено ${formatMoney(props.totalPayments)} · остаток ${formatMoney(props.balanceDue)} · итого ${formatMoney(props.total)} · маржа ${formatMoney(props.margin)}`
));
const candidateBankReceipts = computed(() => (
  bankReceipts.value.filter((receipt) => receipt.status === 'requires_review')
));
const hasDebtForBankReceipts = computed(() => (
  props.balanceDue > 0 && Boolean(props.order.customer?.inn)
));
const hasManualEurRate = computed(() => Boolean(props.currentFxRate?.eur_byn));

const activeFxRate = (currency: PaymentCurrency | null): number | null => {
  if (!props.currentFxRate || !currency) return null;
  if (currency === 'USD') return props.currentFxRate.usd_byn ?? null;
  if (currency === 'EUR') return props.currentFxRate.eur_byn ?? null;
  return null;
};

const notify = (message: string, type: 'success' | 'error') => {
  emit('toast', { message, type });
};

const loadCandidateBankReceipts = async () => {
  const inn = props.order.customer?.inn;
  if (!inn) {
    bankReceipts.value = [];
    return;
  }
  bankReceiptsLoading.value = true;
  try {
    const response = await ManagerMailService.listManagerBankReceipts(
      1,
      20,
      'requires_review',
      inn,
    );
    bankReceipts.value = response.items || [];
  } catch (error) {
    console.error('Failed to load bank receipts', error);
    bankReceipts.value = [];
  } finally {
    bankReceiptsLoading.value = false;
  }
};

watch(
  () => props.order,
  () => void loadCandidateBankReceipts(),
  { immediate: true },
);

const addPayment = async () => {
  if (!newPaymentAmount.value) return;
  if (props.enableCurrency) {
    if (!props.targetCurrency) {
      notify('Сначала выберите валюту сделки', 'error');
      return;
    }
    if (!activeFxRate(props.targetCurrency)) {
      notify('Для выбранной валюты нет доступного курса', 'error');
      return;
    }
  }
  isAddingPayment.value = true;
  try {
    const payments = await ManagerOrdersService.addManagerOrderPayment(
      props.order.id,
      {
        amount: newPaymentAmount.value,
        type: newPaymentType.value,
        currency: props.enableCurrency
          ? (props.targetCurrency || 'USD')
          : 'BYN',
      },
    );
    emit('update:payments', payments);
    newPaymentAmount.value = null;
    notify('Платеж добавлен', 'success');
  } catch (error) {
    notify(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isAddingPayment.value = false;
  }
};

const attachBankReceipt = async (receipt: BankReceiptResponse) => {
  if (!receipt.id) return;
  attachingReceiptId.value = receipt.id;
  try {
    await ManagerMailService.attachManagerBankReceipt(receipt.id, {
      order_id: props.order.id,
      payment_type: 'postpayment',
    });
    notify('Поступление прикреплено к заказу', 'success');
    await loadCandidateBankReceipts();
    emit('reload', props.order.id);
  } catch (error) {
    notify(`Ошибка привязки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    attachingReceiptId.value = null;
  }
};

const receiptCandidateHint = (receipt: BankReceiptResponse) => {
  const meta = receipt.match_meta as any;
  const documents = Array.isArray(meta?.document_candidates)
    ? meta.document_candidates
    : [];
  if (documents.length) {
    const document = documents[0];
    return `${document.doc_type || 'документ'} ${document.number || ''} · заказ #${document.order_id}`;
  }
  const orderIds = Array.isArray(meta?.candidate_order_ids)
    ? meta.candidate_order_ids
    : [];
  return orderIds.length ? `кандидат: заказ #${orderIds[0]}` : '';
};

const formatReceiptDate = (value?: string | null) => {
  if (!value) return 'дата не указана';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatPaymentType = (value?: string | null) => (
  value === 'prepayment' ? 'Аванс' : 'Доплата'
);

const formatBankPaymentDate = (value?: string | null) => {
  if (!value) return 'дата не указана';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const openBankReceiptJournal = (payment: PaymentResponse) => {
  if (!payment.bank_receipt_id) return;
  window.history.pushState({}, '', `/manager/payments?orderId=${props.order.id}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const deletePayment = async (paymentId: number) => {
  try {
    const payments = await ManagerOrdersService.deleteManagerOrderPayment(
      props.order.id,
      paymentId,
    );
    emit('update:payments', payments);
    deletingPaymentId.value = null;
    notify('Платеж удален', 'success');
  } catch (error) {
    notify(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  }
};
</script>

<template>
  <OrderDrawerSection
    id="order-workspace-payments"
    v-model:expanded="expandedModel"
    title="Оплаты"
    :summary="summary"
    icon="account_balance_wallet"
    tone="default"
  >
    <section
      class="rounded-2xl border border-slate-200 bg-slate-50 p-3 shadow-sm sm:p-5"
      data-testid="order-payments-panel"
    >
      <div v-if="isB2cCustomer" class="mb-4 flex justify-end">
        <label class="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:bg-slate-50">
          <input v-model="enableCurrencyModel" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
          Считать в валюте
        </label>
      </div>

      <div v-if="enableCurrency" class="mb-5 rounded-xl border border-blue-100 bg-blue-50/30 p-3 sm:p-4">
        <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-4">
          <label class="field-label !mb-0 text-xs sm:w-1/3">
            Валюта
            <select v-model="targetCurrencyModel" class="field-input mt-1">
              <option value="USD">USD ($)</option>
              <option value="EUR" :disabled="!hasManualEurRate">EUR (€)</option>
            </select>
          </label>
          <label class="field-label !mb-0 flex-1 text-xs">
            Зафиксировать сумму
            <div class="relative">
              <input v-model.number="targetCurrencyAmountModel" type="number" step="0.01" min="0" class="field-input mt-1 w-full" placeholder="Итоговая сумма в валюте" />
              <span v-if="currentFxRate?.usd_byn && targetCurrency === 'USD'" class="absolute right-3 top-1/2 -translate-y-1/2 rounded bg-blue-50/80 px-1 text-[10px] font-medium text-blue-400" title="Текущий курс NBRB">Курс: {{ currentFxRate.usd_byn }}</span>
              <span v-else-if="currentFxRate?.eur_byn && targetCurrency === 'EUR'" class="absolute right-3 top-1/2 -translate-y-1/2 rounded bg-blue-50/80 px-1 text-[10px] font-medium text-blue-400" title="Текущий курс NBRB">Курс: {{ currentFxRate.eur_byn }}</span>
            </div>
          </label>
        </div>
        <p v-if="targetCurrency === 'EUR' && !hasManualEurRate" class="text-xs text-amber-700">
          EUR недоступен при ручном источнике курса. Переключите источник курса на NBRB.
        </p>
        <div class="flex flex-col gap-3 border-t border-blue-100 pt-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="sm:w-1/2">
            <p class="mb-1 text-xs uppercase tracking-wide text-slate-500">Внесено оплат ({{ targetCurrency || 'USD' }})</p>
            <p class="text-xl font-bold text-gray-800">{{ calculatedTargetCurrencyPayments.toFixed(2) }}</p>
          </div>
          <div class="sm:text-right">
            <p class="mb-1 text-xs uppercase tracking-wide text-slate-500">Остаток долга ({{ targetCurrency || 'USD' }})</p>
            <p class="text-2xl font-bold" :class="targetCurrencyBalanceDue > 0 ? 'text-red-500' : 'text-blue-600'">
              {{ targetCurrencyBalanceDue.toFixed(2) }}
            </p>
          </div>
        </div>
      </div>

      <div class="mt-3 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm sm:flex-row sm:items-end">
        <label class="field-label !mb-0 flex-1 text-xs">
          Внести платеж ({{ enableCurrency ? (targetCurrency || 'USD') : 'BYN' }})
          <input v-model.number="newPaymentAmount" data-testid="payment-amount" type="number" step="0.01" min="0" class="field-input mt-1 shadow-sm" placeholder="0.00" />
        </label>
        <label class="field-label !mb-0 text-xs sm:w-1/3">
          Тип
          <select v-model="newPaymentType" class="field-input mt-1 shadow-sm">
            <option value="prepayment">Аванс</option>
            <option value="postpayment">Доплата</option>
          </select>
        </label>
        <button type="button" data-testid="add-payment" class="btn-mini h-[38px] w-full sm:w-[100px]" :disabled="!newPaymentAmount || isAddingPayment" @click="addPayment">Внести</button>
      </div>

      <div v-if="hasDebtForBankReceipts" class="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-amber-900">Банковские поступления по УНП</p>
            <p class="text-xs text-amber-700">Можно прикрепить поступление, которое требует ручной проверки.</p>
          </div>
          <span v-if="bankReceiptsLoading" class="material-icons-round animate-spin text-amber-600">refresh</span>
        </div>
        <div v-if="candidateBankReceipts.length" class="space-y-2">
          <div v-for="receipt in candidateBankReceipts" :key="receipt.id" class="rounded-lg border border-amber-100 bg-white p-3 text-xs shadow-sm">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-bold text-slate-900">{{ formatMoney(receipt.amount) }}</span>
                  <span class="text-slate-500">{{ formatReceiptDate(receipt.received_at) }}</span>
                  <span v-if="receipt.payment_document_number" class="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-500">№ {{ receipt.payment_document_number }}</span>
                </div>
                <p v-if="receiptCandidateHint(receipt)" class="mt-1 text-amber-700">{{ receiptCandidateHint(receipt) }}</p>
                <p class="mt-1 line-clamp-2 text-slate-500">{{ receipt.payment_purpose || 'Назначение не указано' }}</p>
              </div>
              <button type="button" :data-testid="`attach-receipt-${receipt.id}`" class="btn-mini h-8 shrink-0" :disabled="attachingReceiptId === receipt.id" @click="attachBankReceipt(receipt)">
                {{ attachingReceiptId === receipt.id ? '...' : 'Прикрепить' }}
              </button>
            </div>
          </div>
        </div>
        <div v-else-if="!bankReceiptsLoading" class="rounded-lg border border-dashed border-amber-200 bg-white/70 p-3 text-center text-xs text-amber-700">
          Нет неподтвержденных поступлений по УНП {{ order.customer?.inn }}
        </div>
      </div>

      <div class="mt-4 max-h-56 space-y-2 overflow-y-auto pr-1">
        <div v-for="payment in payments" :key="payment.id" class="rounded-lg border border-slate-100 bg-white px-3 py-2 text-xs shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-slate-500">{{ new Date(payment.date).toLocaleDateString() }}</span>
              <span v-if="payment.bank_receipt" class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">
                <span class="material-icons-round text-[13px]">account_balance</span>
                Банк
              </span>
            </div>
            <span class="font-bold text-slate-800" :class="payment.currency !== 'BYN' ? 'text-blue-600' : ''">
              <template v-if="payment.currency !== 'BYN'">{{ payment.amount.toFixed(2) }} {{ payment.currency }}</template>
              <template v-else>{{ formatMoney(payment.amount) }}</template>
            </span>
            <span class="w-16 text-right text-slate-400">{{ formatPaymentType(payment.type) }}</span>
            <div v-if="deletingPaymentId === payment.id" class="ml-2 flex items-center gap-2">
              <button type="button" class="font-medium text-slate-500 hover:text-slate-800" @click="deletingPaymentId = null">Отмена</button>
              <button type="button" :data-testid="`delete-payment-${payment.id}`" class="font-bold text-red-500 hover:text-red-700" @click="deletePayment(payment.id)">Да, удалить</button>
            </div>
            <button v-else type="button" class="ml-2 flex h-6 w-6 items-center justify-center rounded text-red-400 transition-colors hover:bg-red-50 hover:text-red-600" title="Удалить платеж" @click="deletingPaymentId = payment.id">
              <span class="material-icons-round text-[14px]">delete</span>
            </button>
          </div>
          <div v-if="payment.bank_receipt" class="mt-2 rounded-lg border border-emerald-100 bg-emerald-50/40 p-2 text-[11px] text-slate-600">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-semibold text-emerald-800">ПП № {{ payment.bank_receipt.payment_document_number || payment.bank_receipt.payment_document_raw || payment.bank_receipt.id }}</span>
              <span>{{ formatBankPaymentDate(payment.bank_receipt.received_at || payment.date) }}</span>
              <span v-if="payment.bank_receipt.payer_unp">УНП {{ payment.bank_receipt.payer_unp }}</span>
            </div>
            <p v-if="payment.bank_receipt.payer_name" class="mt-1 truncate font-medium text-slate-700">{{ payment.bank_receipt.payer_name }}</p>
            <p v-if="payment.bank_receipt.payment_purpose" class="mt-1 line-clamp-2 text-slate-500">{{ payment.bank_receipt.payment_purpose }}</p>
            <button type="button" class="mt-1 inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-900" @click="openBankReceiptJournal(payment)">
              <span class="material-icons-round text-[13px]">receipt_long</span>
              Открыть в журнале
            </button>
          </div>
          <p v-else-if="payment.comment" class="mt-1 text-[11px] text-slate-500">{{ payment.comment }}</p>
        </div>
        <div v-if="!payments.length" class="rounded-xl border border-dashed border-gray-200 py-3 text-center text-sm italic text-gray-500">
          Нет оплат
        </div>
      </div>
    </section>
  </OrderDrawerSection>
</template>
