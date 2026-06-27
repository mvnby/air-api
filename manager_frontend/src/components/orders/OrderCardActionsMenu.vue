<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { MoreVertical, XCircle } from 'lucide-vue-next';
import type { ManagerOrderListItemResponse } from '../../client';
import {
  EXECUTION_STATUS_OPTIONS,
  NEGOTIATION_STATUS_OPTIONS,
  formatMoney,
  getOrderBoardColumn,
  getOrderExecutionStatus,
  getOrderNegotiationStatus,
} from './order-utils';

const props = defineProps<{
  order: ManagerOrderListItemResponse;
  allowCloseDebt?: boolean;
}>();

const emit = defineEmits<{
  cancelOrder: [payload: { orderId: number }];
  quickStatus: [payload: { orderId: number; status: string }];
  closeDebt: [payload: { orderId: number }];
}>();

const menuOpen = ref(false);
const menuRoot = ref<HTMLElement | null>(null);
const balanceDue = computed(() => Number(props.order.balance_due || 0));
const activeBoardColumn = computed(() => getOrderBoardColumn(props.order));
const activeNegotiationStatus = computed(() => getOrderNegotiationStatus(props.order));
const activeExecutionStatus = computed(() => getOrderExecutionStatus(props.order));
const stageTitle = computed(() => {
  if (activeBoardColumn.value === 'execution') return 'Работы';
  if (activeBoardColumn.value === 'negotiation') return 'Переговоры';
  return '';
});
const stageOptions = computed(() => {
  if (activeBoardColumn.value === 'execution') return EXECUTION_STATUS_OPTIONS;
  if (activeBoardColumn.value === 'negotiation') return NEGOTIATION_STATUS_OPTIONS;
  return [];
});
const boardActions = computed(() => [
  activeBoardColumn.value !== 'negotiation'
    ? { value: 'negotiation', label: 'Вернуть в переговоры', icon: 'forum' }
    : null,
  activeBoardColumn.value !== 'execution'
    ? { value: 'execution', label: 'Перенести в работы', icon: 'construction' }
    : null,
  activeBoardColumn.value !== 'closed_won'
    ? { value: 'closed_won', label: 'Завершить успешно', icon: 'check_circle' }
    : null,
].filter(Boolean) as Array<{ value: string; label: string; icon: string }>);

const selectStatus = (status: string) => {
  menuOpen.value = false;
  emit('quickStatus', { orderId: props.order.id, status });
};

const selectStageStatus = (status: string) => {
  if (activeBoardColumn.value === 'execution') {
    selectStatus(`execution:${status}`);
    return;
  }
  selectStatus(status);
};

const cancelOrder = () => {
  menuOpen.value = false;
  emit('cancelOrder', { orderId: props.order.id });
};

const closeDebt = () => {
  menuOpen.value = false;
  emit('closeDebt', { orderId: props.order.id });
};

const closeOnOutsideClick = (event: MouseEvent) => {
  if (!menuOpen.value) return;
  const target = event.target instanceof Node ? event.target : null;
  if (target && menuRoot.value?.contains(target)) return;
  menuOpen.value = false;
};

const closeOnEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape') menuOpen.value = false;
};

onMounted(() => {
  document.addEventListener('click', closeOnOutsideClick);
  document.addEventListener('keydown', closeOnEscape);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', closeOnOutsideClick);
  document.removeEventListener('keydown', closeOnEscape);
});
</script>

<template>
  <div ref="menuRoot" class="relative">
    <button
      type="button"
      class="rounded-full p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-slate-700 dark:hover:text-white"
      aria-label="Действия с заказом"
      @click.stop="menuOpen = !menuOpen"
    >
      <MoreVertical class="h-4 w-4" />
    </button>

    <div
      v-if="menuOpen"
      class="absolute right-0 top-7 z-30 w-64 rounded-xl border border-gray-200 bg-white p-1.5 text-xs shadow-xl dark:border-slate-700 dark:bg-slate-800"
      @click.stop
    >
      <template v-if="boardActions.length">
        <div class="px-2 pb-1 pt-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">Быстрая смена</div>
        <button
          v-for="action in boardActions"
          :key="action.value"
          type="button"
          class="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left font-semibold text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
          @click="selectStatus(action.value)"
        >
          <span class="material-icons-round text-[16px]">{{ action.icon }}</span>
          {{ action.label }}
        </button>
      </template>
      <template v-if="stageOptions.length">
        <div v-if="boardActions.length" class="my-1 border-t border-slate-100 dark:border-slate-700" />
        <div class="px-2 pb-1 pt-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">{{ stageTitle }}</div>
      </template>
      <button
        v-for="option in stageOptions"
        :key="option.value"
        type="button"
        class="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left font-semibold text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
        :class="(activeBoardColumn === 'execution' ? activeExecutionStatus : activeNegotiationStatus) === option.value ? 'bg-slate-50 dark:bg-slate-700' : ''"
        @click="selectStageStatus(option.value)"
      >
        <span class="inline-flex min-w-0 items-center gap-2">
          <span class="material-icons-round text-[16px]">{{ option.icon }}</span>
          <span class="truncate">{{ option.label }}</span>
        </span>
        <span v-if="(activeBoardColumn === 'execution' ? activeExecutionStatus : activeNegotiationStatus) === option.value" class="material-icons-round text-[15px] text-teal-600">check</span>
      </button>

      <template v-if="allowCloseDebt && balanceDue > 0">
        <div class="my-1 border-t border-slate-100 dark:border-slate-700" />
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left font-semibold text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-500/10"
          @click="closeDebt"
        >
          <span class="material-icons-round text-[16px]">payments</span>
          Закрыть долг {{ formatMoney(balanceDue) }}
        </button>
      </template>

      <div class="my-1 border-t border-slate-100 dark:border-slate-700" />
      <button
        type="button"
        class="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left font-semibold text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
        @click="cancelOrder"
      >
        <XCircle class="h-4 w-4" />
        Пометить отказом
      </button>
    </div>
  </div>
</template>
