<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { ManagerOrdersService, ManagerMailService } from '../../client';
import type { BankReceiptResponse, ManagerOrderDetailResponse } from '../../client';
import { formatMoney } from './order-utils';
import DateTimeField from '../ui/DateTimeField.vue';
import OrderDocumentsPanel from './OrderDocumentsPanel.vue';
import { getApiErrorMessage } from '../../utils/api-errors';
import { fromLocalDateTimeInput } from '../../utils/datetime';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
}>();

const emit = defineEmits<{
  refresh: [];
  close: [];
}>();

// Refs and UI state
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
const setToast = (msg: string, type: 'success' | 'error' = 'success') => {
  toast.value = msg;
  toastType.value = type;
  setTimeout(() => { toast.value = ''; }, 3000);
};

const showAddStage = ref(false);
const newStageName = ref('');
const newStageStart = ref('');
const newStageInstaller = ref<number | null>(null);

const addStage = async () => {
    if (!newStageName.value) return;
    try {
        await ManagerOrdersService.createManagerOrderStage(props.order.id, {
            name: newStageName.value,
            start_time: fromLocalDateTimeInput(newStageStart.value) || undefined,
            installer_id: newStageInstaller.value,
        });
        showAddStage.value = false;
        newStageName.value = '';
        newStageStart.value = '';
        newStageInstaller.value = null;
        emit('refresh');
        setToast('Этап добавлен');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const updateStageStatus = async (stageId: number, newStatus: string) => {
    try {
        await ManagerOrdersService.updateManagerOrderStage(props.order.id, stageId, {
            status: newStatus
        });
        emit('refresh');
        setToast('Статус обновлен');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const deleteStage = async (stageId: number, stageName: string) => {
    if (!window.confirm(`Удалить выезд «${stageName}»?`)) return;
    try {
        await ManagerOrdersService.deleteManagerOrderStage(props.order.id, stageId);
        emit('refresh');
        setToast('Выезд удален');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const updateEquipmentStatus = async (newStatus: string) => {
    try {
        await ManagerOrdersService.patchManagerOrder(props.order.id, {
            equipment_status: newStatus
        });
        emit('refresh');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const toggleKit = async (val: boolean) => {
    try {
        await ManagerOrdersService.patchManagerOrder(props.order.id, {
            standard_install_kit_issued: val
        });
        emit('refresh');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const closeDeal = async () => {
    try {
        await ManagerOrdersService.patchManagerOrder(props.order.id, {
            status: 'closed',
            closing_result: 'won'
        });
        setToast('Сделка успешна закрыта!');
        emit('refresh');
        emit('close');
    } catch (e: any) {
        setToast(`Ошибка: ${getApiErrorMessage(e)}`, 'error');
    }
};

const payments = computed(() => props.order.payments || []);
const bankReceipts = ref<BankReceiptResponse[]>([]);
const bankReceiptsLoading = ref(false);
const attachingReceiptId = ref<number | null>(null);
const newPaymentAmount = ref<number | null>(null);
const newPaymentType = ref<string>('postpayment');
const isAddingPayment = ref(false);
type PaymentCurrencyValue = 'BYN' | 'USD' | 'EUR';

const paymentCurrency = computed<PaymentCurrencyValue>(() => {
  const currency = props.order.target_currency;
  return currency === 'USD' || currency === 'EUR' ? currency : 'BYN';
});

const formatPaymentAmount = (amount: number | null | undefined, currency?: string | null) => (
  currency && currency !== 'BYN'
    ? `${Number(amount || 0).toFixed(2)} ${currency}`
    : formatMoney(amount || 0)
);

const addPayment = async () => {
  if (!newPaymentAmount.value || isAddingPayment.value) return;
  isAddingPayment.value = true;
  try {
    await ManagerOrdersService.addManagerOrderPayment(props.order.id, {
        amount: newPaymentAmount.value,
        type: newPaymentType.value,
        currency: paymentCurrency.value,
    });
    newPaymentAmount.value = null;
    emit('refresh');
    setToast('Платеж добавлен');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isAddingPayment.value = false;
  }
};

const loadCandidateBankReceipts = async () => {
  const inn = props.order.customer?.inn;
  if (!inn) {
    bankReceipts.value = [];
    return;
  }
  bankReceiptsLoading.value = true;
  try {
    const response = await ManagerMailService.listManagerBankReceipts(1, 20, 'requires_review', inn);
    bankReceipts.value = response.items || [];
  } catch (error) {
    console.error('Failed to load bank receipts', error);
    bankReceipts.value = [];
  } finally {
    bankReceiptsLoading.value = false;
  }
};

const attachBankReceipt = async (receipt: BankReceiptResponse) => {
  attachingReceiptId.value = receipt.id;
  try {
    await ManagerMailService.attachManagerBankReceipt(receipt.id, {
      order_id: props.order.id,
      payment_type: 'postpayment',
    });
    await loadCandidateBankReceipts();
    emit('refresh');
    setToast('Поступление прикреплено');
  } catch (error) {
    setToast(`Ошибка привязки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    attachingReceiptId.value = null;
  }
};

const receiptCandidateHint = (receipt: BankReceiptResponse) => {
  const meta = receipt.match_meta as any;
  const docs = Array.isArray(meta?.document_candidates) ? meta.document_candidates : [];
  if (docs.length) {
    const doc = docs[0];
    return `${doc.doc_type || 'документ'} ${doc.number || ''} · заказ #${doc.order_id}`;
  }
  const ids = Array.isArray(meta?.candidate_order_ids) ? meta.candidate_order_ids : [];
  if (ids.length) return `кандидат: заказ #${ids[0]}`;
  return '';
};

const formatReceiptDate = (value?: string | null) => {
  if (!value) return 'дата не указана';
  return new Date(value).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const formatPaymentType = (value?: string | null) => (value === 'prepayment' ? 'Аванс' : 'Доплата');

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

const openBankReceiptJournal = () => {
  window.history.pushState({}, '', `/manager/payments?orderId=${props.order.id}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

// Load execution helpers on mount
watch(() => props.order.id, () => {
  loadCandidateBankReceipts();
}, { immediate: true });
</script>

<template>
<div class="space-y-6">
  <Transition name="fade">
    <div v-if="toast" class="fixed top-6 right-6 z-[100] text-white px-6 py-3 rounded-xl shadow-2xl font-medium" :class="toastType === 'success' ? 'bg-teal-600' : 'bg-red-500'">
      {{ toast }}
    </div>
  </Transition>

  <div v-if="order.is_on_hold" class="rounded-xl border border-amber-300 bg-amber-50 p-4 mb-4 flex items-center justify-between">
    <div>
        <h4 class="text-amber-800 font-bold mb-1">Сделка на паузе</h4>
        <p class="text-sm text-amber-700">{{ order.on_hold_reason || 'Ожидает действий клиента или менеджера' }}</p>
    </div>
  </div>

  <!-- ZONE 1: Timeline -->
  <section class="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
    <div class="flex items-center justify-between mb-4 border-b border-slate-100 pb-3">
        <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk']">Хронология выездов</h3>
        <button v-if="!showAddStage" class="btn-mini" @click="showAddStage = true">+ Добавить выезд</button>
    </div>

    <!-- Timeline List -->
    <div class="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">
        <div v-for="stage in order.work_stages" :key="stage.id" class="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
            <div class="flex items-center justify-center w-10 h-10 rounded-full border border-white shrink-0 shadow z-10" :class="stage.status === 'canceled' ? 'bg-slate-400' : 'bg-teal-500'" >
                <span class="material-icons-round text-[20px] text-white">{{ stage.status === 'completed' ? 'check' : (stage.status === 'canceled' ? 'close' : (stage.status === 'in_progress' ? 'build' : 'schedule')) }}</span>
            </div>
            
            <div class="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border border-slate-200 bg-slate-50 shadow text-sm" :class="{ 'opacity-50': stage.status === 'canceled' }">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-bold text-slate-800">{{ stage.name }}</span>
                    <div class="flex items-center gap-1">
                        <select :value="stage.status" @change="updateStageStatus(stage.id, ($event.target as HTMLSelectElement).value)" class="text-xs bg-white border border-slate-300 rounded px-1 py-0.5 text-slate-700">
                            <option value="planned">Планируется</option>
                            <option value="in_progress">В работе</option>
                            <option value="completed">Выполнено</option>
                            <option value="canceled">Отменено</option>
                        </select>
                        <button @click="deleteStage(stage.id, stage.name)" class="text-slate-400 hover:text-red-500 transition-colors p-0.5" title="Удалить выезд">
                            <span class="material-icons-round text-[16px]">delete_outline</span>
                        </button>
                    </div>
                </div>
                <div class="text-slate-500 text-xs mt-1">
                    {{ stage.start_time ? new Date(stage.start_time).toLocaleString() : 'План: не задан' }}
                </div>
            </div>
        </div>
        
        <div v-if="!order.work_stages?.length && !showAddStage" class="text-center py-6 text-slate-500 italic">
            Нет запланированных выездов. Начните планирование.
        </div>
    </div>

    <!-- Add Form -->
    <div v-if="showAddStage" class="mt-4 p-4 border border-teal-200 bg-teal-50/30 rounded-xl">
        <h4 class="font-bold text-teal-800 mb-3 text-sm">Новый выезд</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <label class="field-label !mb-0 text-xs">Название (Этап)
                <select v-model="newStageName" class="field-input mt-1">
                    <option value="" disabled>Выберите из пресетов...</option>
                    <option value="Монтаж 'под ключ'">Монтаж 'под ключ'</option>
                    <option value="Закладка трассы (Черновой)">Закладка трассы (Черновой)</option>
                    <option value="Навеска блоков (Чистовой)">Навеска блоков (Чистовой)</option>
                    <option value="Доп. выезд">Доп. выезд</option>
                </select>
            </label>
            <DateTimeField v-model="newStageStart" label="Дата и время" />
        </div>
        <div class="flex items-center gap-2 justify-end">
            <button class="btn-mini-outline" @click="showAddStage = false">Отмена</button>
            <button class="btn-mini" :disabled="!newStageName" @click="addStage">Сохранить</button>
        </div>
    </div>
  </section>

  <!-- ZONE 2: Picking List -->
  <section class="rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
      <div class="flex flex-col md:flex-row items-start md:items-center justify-between mb-4 border-b border-slate-100 pb-3">
          <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk']">Склад и комплектация</h3>
          
          <div class="flex flex-wrap items-center gap-2 border border-slate-300 bg-slate-50 rounded-lg p-1 mt-3 md:mt-0 w-full md:w-auto">
              <button class="px-3 py-1 flex-1 md:flex-none justify-center rounded text-xs font-medium transition-colors" :class="order.equipment_status === 'pending' ? 'bg-red-500 text-white shadow' : 'text-slate-600 hover:bg-slate-200'" @click="updateEquipmentStatus('pending')">🔴 Не собрано</button>
              <button class="px-3 py-1 flex-1 md:flex-none justify-center rounded text-xs font-medium transition-colors" :class="order.equipment_status === 'reserved' ? 'bg-amber-500 text-white shadow' : 'text-slate-600 hover:bg-slate-200'" @click="updateEquipmentStatus('reserved')">🟡 Забронировано</button>
              <button class="px-3 py-1 flex-1 md:flex-none justify-center rounded text-xs font-medium transition-colors" :class="order.equipment_status === 'issued' ? 'bg-teal-500 text-white shadow' : 'text-slate-600 hover:bg-slate-200'" @click="updateEquipmentStatus('issued')">🟢 Выдано бригаде</button>
          </div>
      </div>

      <div class="bg-slate-50 rounded-xl p-4 border border-slate-200 mb-4">
          <ul class="space-y-2 text-sm text-slate-700">
              <li v-for="link in order.product_lines" :key="link.id" class="flex justify-between items-center bg-white p-2 rounded shadow-sm border border-slate-100">
                  <span class="font-medium flex-1">{{ link.product_title }}</span>
                  <span class="bg-slate-100 px-2 py-0.5 rounded font-bold text-slate-600">{{ link.quantity }} шт.</span>
              </li>
              <li v-if="!order.product_lines?.length" class="text-slate-400 italic py-2">Нет оборудования в смете</li>
          </ul>
      </div>

      <label class="flex items-center gap-2 cursor-pointer bg-slate-50 p-3 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors">
          <input type="checkbox" :checked="order.standard_install_kit_issued" @change="toggleKit(($event.target as HTMLInputElement).checked)" class="w-5 h-5 rounded border-slate-300 text-teal-600 focus:ring-teal-600" />
          <span class="font-medium text-slate-800 text-sm">Выдать стандартный монтажный комплект (Кронштейны, труба и т.д.)</span>
      </label>
  </section>

  <!-- ZONE 3: Finance -->
  <section class="rounded-2xl bg-slate-50 border border-slate-200 p-5 shadow-sm">
          <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk'] mb-4">Финансы</h3>
          <div class="mb-4 text-center border border-slate-200 rounded-xl py-6 bg-white shadow-inner">
              <p class="text-sm font-medium text-slate-500 uppercase tracking-wide">Остаток к оплате</p>
              <p class="text-4xl font-black mt-2 tracking-tight" :class="(order.balance_due || 0) > 0 ? 'text-red-500' : 'text-teal-600'">
                  {{ formatMoney(order.balance_due || 0) }}
              </p>
          </div>
          
          <div class="flex items-end gap-2 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
              <label class="flex-1 field-label !mb-0 text-xs">Внести сумму ({{ paymentCurrency }})
                  <input v-model.number="newPaymentAmount" type="number" min="0" class="field-input mt-1 shadow-sm" placeholder="0.00" />
              </label>
              <button class="btn-mini h-[38px] w-[100px]" :disabled="!newPaymentAmount || isAddingPayment" @click="addPayment">
                {{ isAddingPayment ? '...' : 'Внести' }}
              </button>
          </div>

          <div v-if="(order.balance_due || 0) > 0 && order.customer?.inn" class="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
            <div class="mb-3 flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-amber-900">Поступления по УНП</p>
                <p class="text-xs text-amber-700">Только платежи, которые требуют ручной проверки.</p>
              </div>
              <span v-if="bankReceiptsLoading" class="material-icons-round animate-spin text-amber-600">refresh</span>
            </div>
            <div v-if="bankReceipts.length" class="space-y-2">
              <div v-for="receipt in bankReceipts" :key="receipt.id" class="rounded-lg border border-amber-100 bg-white p-3 text-xs shadow-sm">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-bold text-slate-900">{{ formatMoney(receipt.amount) }}</span>
                      <span class="text-slate-500">{{ formatReceiptDate(receipt.received_at) }}</span>
                      <span v-if="receipt.payment_document_number" class="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-500">№ {{ receipt.payment_document_number }}</span>
                    </div>
                    <p v-if="receiptCandidateHint(receipt)" class="mt-1 text-amber-700">{{ receiptCandidateHint(receipt) }}</p>
                    <p class="mt-1 text-slate-500">{{ receipt.payment_purpose || 'Назначение не указано' }}</p>
                  </div>
                  <button class="btn-mini h-8 shrink-0" :disabled="attachingReceiptId === receipt.id" @click="attachBankReceipt(receipt)">
                    {{ attachingReceiptId === receipt.id ? '...' : 'Прикрепить' }}
                  </button>
                </div>
              </div>
            </div>
            <div v-else-if="!bankReceiptsLoading" class="rounded-lg border border-dashed border-amber-200 bg-white/70 p-3 text-center text-xs text-amber-700">
              Нет неподтвержденных поступлений по УНП {{ order.customer.inn }}
            </div>
          </div>

          <div class="mt-4 space-y-2 max-h-56 overflow-y-auto pr-1">
              <div v-for="p in payments" :key="p.id" class="rounded-lg bg-white border border-slate-100 px-3 py-2 text-xs shadow-sm">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-slate-500">{{ new Date(p.date).toLocaleDateString() }}</span>
                      <span
                        v-if="p.bank_receipt"
                        class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700"
                      >
                        <span class="material-icons-round text-[13px]">account_balance</span>
                        Банк
                      </span>
                    </div>
                    <span class="font-bold text-slate-800" :class="p.currency !== 'BYN' ? 'text-blue-600' : ''">
                      {{ formatPaymentAmount(p.amount, p.currency) }}
                    </span>
                    <span class="text-slate-400 w-16 text-right">{{ formatPaymentType(p.type) }}</span>
                  </div>
                  <div v-if="p.bank_receipt" class="mt-2 rounded-lg border border-emerald-100 bg-emerald-50/40 p-2 text-[11px] text-slate-600">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-semibold text-emerald-800">ПП № {{ p.bank_receipt.payment_document_number || p.bank_receipt.payment_document_raw || p.bank_receipt.id }}</span>
                      <span>{{ formatBankPaymentDate(p.bank_receipt.received_at || p.date) }}</span>
                      <span v-if="p.bank_receipt.payer_unp">УНП {{ p.bank_receipt.payer_unp }}</span>
                    </div>
                    <p v-if="p.bank_receipt.payer_name" class="mt-1 truncate font-medium text-slate-700">{{ p.bank_receipt.payer_name }}</p>
                    <p v-if="p.bank_receipt.payment_purpose" class="mt-1 line-clamp-2 text-slate-500">{{ p.bank_receipt.payment_purpose }}</p>
                    <button class="mt-1 inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-900" @click="openBankReceiptJournal">
                      <span class="material-icons-round text-[13px]">receipt_long</span>
                      Открыть в журнале
                    </button>
                  </div>
              </div>
          </div>
  </section>

  <OrderDocumentsPanel
    :order="order"
    @refresh="emit('refresh')"
    @toast="setToast($event.message, $event.type || 'success')"
  />

  <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <button
      class="flex w-full items-center justify-center gap-2 rounded-xl py-4 text-lg font-bold shadow-lg transition-transform active:scale-95"
      :class="(order.balance_due || 0) > 0 ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-teal-500 text-white hover:bg-teal-600'"
      :disabled="(order.balance_due || 0) > 0"
      :title="(order.balance_due || 0) > 0 ? 'Нельзя закрыть при наличии долга' : 'Завершить сделку'"
      @click="closeDeal"
    >
      <span class="material-icons-round text-[24px]">task_alt</span>
      Завершить сделку
    </button>
    <p v-if="(order.balance_due || 0) > 0" class="mt-2 text-center text-xs font-medium text-red-400">Оплатите остаток для закрытия сделки</p>
  </section>
</div>
</template>
