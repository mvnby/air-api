<script setup lang="ts">
import { ref } from 'vue';
import FullCalendar from '@fullcalendar/vue3';
import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import type { CalendarOptions, EventSourceFunc } from '@fullcalendar/core';
import { ManagerCalendarService, type CalendarEventResponse, type ManagerOrderDetailResponse, type ManagerOrderUpdatePayload } from '../client';
import { api } from '../api';
import { Loader2 } from 'lucide-vue-next';
import OrderEditDrawer from '../components/orders/OrderEditDrawer.vue';
import { parseApiFieldErrors } from '../utils/api-errors';

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

const saveOrder = async (payload: { orderId: number; data: ManagerOrderUpdatePayload }) => {
  if (saving.value) return;
  saving.value = true;
  orderServerErrors.value = {};
  orderFormError.value = '';
  try {
    selectedOrder.value = await api.patchManagerOrder(payload.orderId, payload.data);
    drawerOpen.value = false;
    setToast('Сделка сохранена');
    
    // Refresh events to show updated dates immediately
    const calendarApi = calendarRef.value?.getApi();
    if (calendarApi) {
      calendarApi.refetchEvents();
    }
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
  const calendarApi = calendarRef.value?.getApi();
  if (calendarApi) {
    calendarApi.refetchEvents();
  }
};

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
  plugins: [ dayGridPlugin, interactionPlugin ],
  initialView: 'dayGridMonth',
  locale: 'ru',
  headerToolbar: {
    left: 'prev,next today',
    center: 'title',
    right: 'dayGridMonth,dayGridWeek'
  },
  events: fetchEvents,
  eventClick: handleEventClick,
  height: 'auto',
  firstDay: 1 // Monday
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
