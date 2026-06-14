<script setup lang="ts">
import { onMounted, ref } from 'vue';
import FullCalendar from '@fullcalendar/vue3';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import type { CalendarOptions, EventSourceFunc } from '@fullcalendar/core';
import { ManagerCalendarService, ManagerOrdersService, type CalendarEventResponse, type ManagerOrderDetailResponse, type ManagerOrderUpdatePayload, type ManagerStaleWorkStageItem } from '../client';
import { api } from '../api';
import { Loader2, RefreshCw, Trash2, XCircle } from 'lucide-vue-next';
import OrderEditDrawer from '../components/orders/OrderEditDrawer.vue';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';

const isLoading = ref(false);
const error = ref<string | null>(null);

// Order Drawer State
const drawerOpen = ref(false);
const selectedOrder = ref<ManagerOrderDetailResponse | null>(null);
const orderServerErrors = ref<Record<string, string>>({});
const orderFormError = ref('');
const saving = ref(false);
const toast = ref('');
const calendarRef = ref<any>(null);
const staleStages = ref<ManagerStaleWorkStageItem[]>([]);
const staleStagesTotal = ref(0);
const staleStagesLoading = ref(false);
const staleStagesError = ref('');

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2500);
};

// Event Handling
const handleEventClick = (info: any) => {
  const orderId = info.event.extendedProps.order_id;
  if (orderId) {
    openOrder(orderId);
  } else {
    console.warn('Event clicked without order_id', info.event);
  }
};

const handleEventDrop = async (info: any) => {
  const event = info.event;
  const orderId = event.extendedProps.order_id;
  const type = event.extendedProps.type;
  
  if (!orderId || !type) {
    info.revert();
    return;
  }
  
  const payload: Partial<ManagerOrderUpdatePayload> = {};
  if (type === 'measurement') {
    payload.measurement_date = event.start.toISOString();
  } else if (type === 'installation') {
    payload.installation_date = event.start.toISOString();
  } else {
    info.revert();
    setToast('Невозможно изменить время для этого типа события');
    return;
  }
  
  try {
    await api.patchManagerOrder(orderId, payload);
    setToast('Время изменено');
  } catch (error: any) {
    console.error('Failed to update event time', error);
    const parsed = parseApiFieldErrors(error, []);
    setToast(`Ошибка сохранения: ${parsed.message}`);
    info.revert();
  }
};

const openOrder = async (orderId: number) => {
  try {
    isLoading.value = true;
    orderServerErrors.value = {};
    orderFormError.value = '';
    selectedOrder.value = await api.getManagerOrderDetail(orderId);
    drawerOpen.value = true;
  } catch (err: any) {
    console.error('Failed to open order details', err);
    setToast('Не удалось открыть заказ');
  } finally {
    isLoading.value = false;
  }
};

const loadStaleStages = async () => {
  staleStagesLoading.value = true;
  staleStagesError.value = '';
  try {
    const response = await ManagerOrdersService.listManagerStaleOrderStages(7, true, 100);
    staleStages.value = response.items || [];
    staleStagesTotal.value = response.total || 0;
  } catch (err) {
    console.error('Failed to load stale work stages', err);
    staleStagesError.value = getApiErrorMessage(err);
  } finally {
    staleStagesLoading.value = false;
  }
};

const refreshCalendar = () => {
  const calendarApi = calendarRef.value?.getApi();
  if (calendarApi) {
    calendarApi.refetchEvents();
  }
};

const cancelStaleStage = async (stage: ManagerStaleWorkStageItem) => {
  if (!window.confirm(`Отменить задачу «${stage.name}» по заказу #${stage.order_id}?`)) return;
  try {
    await ManagerOrdersService.cancelManagerOrderStageDirect(stage.id);
    setToast('Задача отменена');
    await loadStaleStages();
    refreshCalendar();
  } catch (err) {
    setToast(`Ошибка отмены: ${getApiErrorMessage(err)}`);
  }
};

const deleteStaleStage = async (stage: ManagerStaleWorkStageItem) => {
  if (!window.confirm(`Удалить задачу «${stage.name}» по заказу #${stage.order_id}?`)) return;
  try {
    await ManagerOrdersService.deleteManagerOrderStageDirect(stage.id);
    setToast('Задача удалена');
    await loadStaleStages();
    refreshCalendar();
  } catch (err) {
    setToast(`Ошибка удаления: ${getApiErrorMessage(err)}`);
  }
};

const saveOrder = async (payload: { orderId: number; data: ManagerOrderUpdatePayload }) => {
  if (saving.value) return;
  saving.value = true;
  orderServerErrors.value = {};
  orderFormError.value = '';
  try {
    selectedOrder.value = await api.patchManagerOrder(payload.orderId, payload.data);
    setToast('Сделка сохранена');
    
    // Refresh events to show updated dates immediately
    refreshCalendar();
  } catch (error: any) {
    console.error(error);
    const parsed = parseApiFieldErrors(error, [
      'status',
      'next_followup_date',
      'measurement_date',
      'installation_date',
      'comment',
      'is_paid',
      'customer_name',
      'customer_phone',
      'customer_email',
      'customer_inn',
      'customer_full_legal_name',
      'customer_legal_address',
      'customer_bank_name',
      'customer_bic',
      'customer_iban',
      'customer_delivery_address',
      'products',
      'services',
    ]);
    orderServerErrors.value = parsed.fieldErrors;
    orderFormError.value = parsed.message;
    setToast(`Ошибка сохранения: ${parsed.message}`);
  } finally {
    saving.value = false;
  }
};

const handleOrderDeleted = (orderId: number) => {
  drawerOpen.value = false;
  if (selectedOrder.value?.id === orderId) {
    selectedOrder.value = null;
  }
  setToast('Сделка удалена');
  refreshCalendar();
};

const formatStageDate = (value?: string | null) => {
  if (!value) return 'дата не задана';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

onMounted(loadStaleStages);

const fetchEvents: EventSourceFunc = async (fetchInfo, successCallback, failureCallback) => {
  isLoading.value = true;
  error.value = null;
  try {
    const events: CalendarEventResponse[] = await ManagerCalendarService.getManagerCalendarEvents(
      fetchInfo.start.toISOString(),
      fetchInfo.end.toISOString()
    );
    
    const mappedEvents = events.map(e => ({
      id: e.id,
      title: e.title,
      start: e.start,
      allDay: e.allDay,
      backgroundColor: e.color,
      borderColor: e.color,
      extendedProps: {
        order_id: e.order_id,
        type: e.type,
        customer_name: e.customer_name,
        address: e.address,
        status: e.status
      }
    }));
    successCallback(mappedEvents);
  } catch (err: any) {
    console.error('Failed to fetch calendar events', err);
    error.value = 'Не удалось загрузить события календаря';
    failureCallback(err);
  } finally {
    isLoading.value = false;
  }
};

const calendarOptions = ref<CalendarOptions>({
  plugins: [ dayGridPlugin, timeGridPlugin, interactionPlugin ],
  initialView: 'dayGridMonth',
  locale: 'ru',
  headerToolbar: {
    left: 'prev,next today',
    center: 'title',
    right: 'dayGridMonth,timeGridWeek,timeGridDay'
  },
  events: fetchEvents,
  eventClick: handleEventClick,
  editable: true,
  eventDurationEditable: false,
  eventDrop: handleEventDrop,
  height: 'auto',
  firstDay: 1, // Monday
  slotMinTime: '08:00:00',
});

</script>

<template>
  <div class="p-6 max-w-[1400px] mx-auto relative min-h-screen">
    <!-- Toast -->
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium animate-in slide-in-from-top-4 duration-300">
        {{ toast }}
      </div>
    </Transition>

    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">calendar_month</span>
        Календарь монтажей и замеров
      </h1>
      <div v-if="isLoading" class="text-teal-600 flex items-center gap-2">
        <Loader2 class="w-5 h-5 animate-spin" />
        Loading...
      </div>
    </div>

    <div v-if="error" class="bg-red-50 text-red-600 p-4 rounded-lg mb-6">
      {{ error }}
    </div>

    <section class="mb-6 rounded-xl border border-amber-200 bg-amber-50/70 p-4 shadow-sm">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 class="text-sm font-bold uppercase tracking-wide text-amber-900">Хвосты рабочих задач</h2>
          <p class="mt-1 text-sm text-amber-800">
            Незавершенные этапы старше 7 дней или без даты: {{ staleStagesTotal }}
          </p>
        </div>
        <button
          class="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-900 shadow-sm transition hover:bg-amber-100 disabled:opacity-60"
          :disabled="staleStagesLoading"
          @click="loadStaleStages"
        >
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': staleStagesLoading }" />
          Обновить
        </button>
      </div>

      <div v-if="staleStagesError" class="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {{ staleStagesError }}
      </div>
      <div v-else-if="staleStagesLoading" class="mt-3 flex items-center gap-2 text-sm text-amber-800">
        <Loader2 class="h-4 w-4 animate-spin" />
        Проверяем задачи...
      </div>
      <div v-else-if="!staleStages.length" class="mt-3 rounded-lg bg-white/70 px-3 py-2 text-sm text-amber-800">
        Просроченных рабочих задач нет.
      </div>
      <div v-else class="mt-4 overflow-x-auto">
        <table class="min-w-full border-separate border-spacing-y-2 text-sm">
          <thead class="text-left text-xs uppercase tracking-wide text-amber-900">
            <tr>
              <th class="px-3 py-1">Задача</th>
              <th class="px-3 py-1">Дата</th>
              <th class="px-3 py-1">Клиент</th>
              <th class="px-3 py-1">Исполнитель</th>
              <th class="px-3 py-1 text-right">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="stage in staleStages" :key="stage.id" class="bg-white shadow-sm">
              <td class="rounded-l-lg px-3 py-3 align-top">
                <button class="font-semibold text-teal-700 hover:text-teal-900" @click="openOrder(stage.order_id)">
                  #{{ stage.order_id }} · {{ stage.name }}
                </button>
                <div class="mt-1 text-xs text-slate-500">
                  {{ stage.order_title || 'Заказ без названия' }} · {{ stage.order_status }}
                </div>
                <div v-if="stage.manager_comment" class="mt-2 max-w-xl text-xs text-slate-600">
                  {{ stage.manager_comment }}
                </div>
              </td>
              <td class="px-3 py-3 align-top text-slate-700">
                {{ formatStageDate(stage.start_time) }}
              </td>
              <td class="px-3 py-3 align-top text-slate-700">
                <div>{{ stage.customer_name || 'Клиент не указан' }}</div>
                <div class="text-xs text-slate-500">{{ stage.customer_phone || 'телефон не указан' }}</div>
                <div class="text-xs text-slate-500">{{ stage.address || 'адрес не указан' }}</div>
              </td>
              <td class="px-3 py-3 align-top text-slate-700">
                {{ stage.installer_name || 'не назначен' }}
              </td>
              <td class="rounded-r-lg px-3 py-3 align-top">
                <div class="flex justify-end gap-2">
                  <button
                    class="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
                    @click="cancelStaleStage(stage)"
                  >
                    <XCircle class="h-4 w-4" />
                    Отменить
                  </button>
                  <button
                    class="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-50"
                    @click="deleteStaleStage(stage)"
                  >
                    <Trash2 class="h-4 w-4" />
                    Удалить
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6 calendar-wrapper">
      <FullCalendar ref="calendarRef" :options="calendarOptions" />
    </div>

    <!-- Edit Drawer -->
    <OrderEditDrawer
      v-model="drawerOpen"
      :order="selectedOrder"
      :server-errors="orderServerErrors"
      :form-error="orderFormError"
      :saving="saving"
      @save="saveOrder"
      @deleted="handleOrderDeleted"
      @reload="openOrder($event)"
    />
  </div>
</template>

<style>
.calendar-wrapper {
  --fc-border-color: #e5e7eb;
  --fc-button-text-color: #374151;
  --fc-button-bg-color: #ffffff;
  --fc-button-border-color: #d1d5db;
  --fc-button-hover-bg-color: #f9fafb;
  --fc-button-hover-border-color: #d1d5db;
  --fc-button-active-bg-color: #f3f4f6;
  --fc-button-active-border-color: #d1d5db;
  --fc-today-bg-color: #f0fdfa;
  --fc-event-border-color: transparent;
}

.fc-button-primary {
  @apply !bg-white !border-gray-300 !text-gray-700 !shadow-sm hover:!bg-gray-50 focus:!ring-2 focus:!ring-teal-500 focus:!ring-offset-1 !transition-colors;
}

.fc-button-primary:not(:disabled).fc-button-active, 
.fc-button-primary:not(:disabled):active {
  @apply !bg-gray-100 !border-gray-300 !text-gray-900 !shadow-inner;
}

.fc-toolbar-title {
  @apply !text-xl !font-bold !text-gray-900;
}

.fc-col-header-cell-cushion {
  @apply !text-gray-500 !font-medium !py-3;
}

.fc-daygrid-day-number {
  @apply !text-gray-700 !font-medium !p-2;
}

.fc-event {
  @apply !shadow-sm !rounded !px-1 !py-0.5 !cursor-pointer hover:!opacity-90 transition-opacity;
}

/* Toast Animation */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
