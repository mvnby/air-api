<script setup lang="ts">
import { ref, computed } from 'vue';
import { ManagerOrdersService } from '../../client';
import type { ManagerOrderDetailResponse } from '../../client';
import { formatMoney } from './order-utils';
import DateTimeField from '../ui/DateTimeField.vue';
import { getApiErrorMessage } from '../../utils/api-errors';

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
            start_time: newStageStart.value ? newStageStart.value + ':00Z' : undefined,
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
const newPaymentAmount = ref<number | null>(null);
const newPaymentType = ref<string>('postpayment');

const addPayment = async () => {
  if (!newPaymentAmount.value) return;
  try {
    await ManagerOrdersService.addManagerOrderPayment(props.order.id, {
        amount: newPaymentAmount.value,
        type: newPaymentType.value,
    });
    newPaymentAmount.value = null;
    emit('refresh');
    setToast('Платеж добавлен');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  }
};

const generateDocument = async (type: string) => {
  try {
    const res = await ManagerOrdersService.generateManagerOrderDocument(props.order.id, type);
    window.open(res.edit_url, '_blank');
    emit('refresh');
  } catch (error) {
    setToast(`Ошибка генерации: ${getApiErrorMessage(error)}`, 'error');
  }
};
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
        <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk']">Зона 1: Хронология выездов</h3>
        <button v-if="!showAddStage" class="btn-mini" @click="showAddStage = true">+ Добавить выезд</button>
    </div>

    <!-- Timeline List -->
    <div class="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">
        <div v-for="stage in order.work_stages" :key="stage.id" class="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
            <div class="flex items-center justify-center w-10 h-10 rounded-full border border-white shrink-0 shadow bg-teal-500 text-white z-10">
                <span class="material-icons-round text-[20px]">{{ stage.status === 'completed' ? 'check' : (stage.status === 'in_progress' ? 'build' : 'schedule') }}</span>
            </div>
            
            <div class="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border border-slate-200 bg-slate-50 shadow text-sm">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-bold text-slate-800">{{ stage.name }}</span>
                    <select :value="stage.status" @change="updateStageStatus(stage.id, ($event.target as HTMLSelectElement).value)" class="text-xs bg-white border border-slate-300 rounded px-1 py-0.5 text-slate-700">
                        <option value="planned">Планируется</option>
                        <option value="in_progress">В работе</option>
                        <option value="completed">Выполнено</option>
                        <option value="canceled">Отменено</option>
                    </select>
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
          <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk']">Зона 2: Склад и Комплектация</h3>
          
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
  <section class="rounded-2xl bg-white border border-slate-200 shadow-sm overflow-hidden flex flex-col md:flex-row">
      <div class="flex-1 p-5 border-b md:border-b-0 md:border-r border-slate-200 bg-slate-50">
          <h3 class="text-lg font-bold text-slate-800 font-['Space_Grotesk'] mb-4">Зона 3: Финансы</h3>
          <div class="mb-4 text-center border border-slate-200 rounded-xl py-6 bg-white shadow-inner">
              <p class="text-sm font-medium text-slate-500 uppercase tracking-wide">Остаток к оплате</p>
              <p class="text-4xl font-black mt-2 tracking-tight" :class="(order.balance_due || 0) > 0 ? 'text-red-500' : 'text-teal-600'">
                  {{ formatMoney(order.balance_due || 0) }}
              </p>
          </div>
          
          <div class="flex items-end gap-2 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
              <label class="flex-1 field-label !mb-0 text-xs">Внести сумму
                  <input v-model.number="newPaymentAmount" type="number" min="0" class="field-input mt-1 shadow-sm" placeholder="0.00" />
              </label>
              <button class="btn-mini h-[38px] w-[100px]" :disabled="!newPaymentAmount" @click="addPayment">Внести</button>
          </div>

          <div class="mt-4 space-y-2 max-h-32 overflow-y-auto pr-1">
              <div v-for="p in payments" :key="p.id" class="flex justify-between items-center text-xs py-2 px-3 rounded-lg bg-white border border-slate-100 shadow-sm">
                  <span class="text-slate-500">{{ new Date(p.date).toLocaleDateString() }}</span>
                  <span class="font-bold text-slate-800">{{ formatMoney(p.amount) }}</span>
                  <span class="text-slate-400 w-16 text-right">{{ p.type === 'prepayment' ? 'Аванс' : 'Доплата' }}</span>
              </div>
          </div>
      </div>

      <div class="flex-1 p-5 flex flex-col items-center justify-center bg-white space-y-4">
          <div class="w-full space-y-3">
              <button class="w-full flex items-center justify-center gap-2 py-3 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl transition-colors border border-slate-200" @click="generateDocument('act')">
                  <span class="material-icons-round text-[20px] text-amber-500">description</span> 
                  Акт выполненных работ
              </button>
              <button class="w-full flex items-center justify-center gap-2 py-3 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl transition-colors border border-slate-200" @click="generateDocument('tn2')">
                  <span class="material-icons-round text-[20px] text-blue-500">receipt</span> 
                  ТН-2 / Гарантийный талон
              </button>
          </div>
          
          <hr class="w-full border-slate-100 my-2" />
          
          <button 
                class="w-full py-4 rounded-xl text-lg font-bold shadow-lg flex items-center justify-center gap-2 transition-transform active:scale-95" 
                :class="(order.balance_due || 0) > 0 ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-teal-500 text-white hover:bg-teal-600'"
                :disabled="(order.balance_due || 0) > 0"
                @click="closeDeal"
                :title="(order.balance_due || 0) > 0 ? 'Нельзя закрыть при наличии долга' : 'Завершить сделку'"
            >
              <span class="material-icons-round text-[24px]">task_alt</span> Завершить сделку
          </button>
          <p v-if="(order.balance_due || 0) > 0" class="text-xs text-red-400 font-medium text-center">Оплатите остаток для закрытия сделки</p>
      </div>
  </section>
</div>
</template>
