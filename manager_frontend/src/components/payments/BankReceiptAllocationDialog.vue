<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { Check, ListOrdered, LoaderCircle, RotateCcw, Scale, X } from 'lucide-vue-next';
import type {
  BankReceiptAllocationDetailResponse,
  BankReceiptAllocationOrderResponse,
  BankReceiptAllocationPayload,
} from '../../client';
import { useDialogA11y } from '../../composables/useDialogA11y';

type AllocationRow = BankReceiptAllocationOrderResponse & {
  selected: boolean;
  amount: number;
};

const props = defineProps<{
  open: boolean;
  detail: BankReceiptAllocationDetailResponse | null;
  loading: boolean;
  saving: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  save: [allocations: BankReceiptAllocationPayload[]];
}>();

const rows = reactive<AllocationRow[]>([]);
const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);

const money = (value?: number | null) => new Intl.NumberFormat('ru-BY', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
}).format(Number(value || 0));

const currency = computed(() => props.detail?.currency || 'BYN');
const allocated = computed(() => rows.reduce((sum, row) => sum + (row.selected ? Number(row.amount || 0) : 0), 0));
const remainder = computed(() => Math.max(0, Number(props.detail?.receipt_amount || 0) - allocated.value));
const changed = computed(() => rows.some((row) => (
  Math.abs((row.selected ? Number(row.amount || 0) : 0) - Number(row.current_allocation || 0)) > 0.005
)));
const validationError = computed(() => {
  if (!props.detail) return '';
  if (allocated.value - props.detail.receipt_amount > 0.005) {
    return 'Распределение превышает сумму банковского поступления.';
  }
  const excessive = rows.find((row) => (
    row.selected && Number(row.amount || 0) - Number(row.balance_due_before_receipt || 0) > 0.005
  ));
  if (excessive) {
    return `По заказу #${excessive.order_id} указано больше его задолженности.`;
  }
  return '';
});
const canSave = computed(() => (
  Boolean(props.detail)
  && changed.value
  && !validationError.value
  && !props.loading
  && !props.saving
));

watch(
  () => [props.open, props.detail] as const,
  ([open, detail]) => {
    if (!open || !detail) return;
    rows.splice(0, rows.length, ...(detail.orders || []).map((order) => ({
      ...order,
      selected: Number(order.current_allocation || 0) > 0,
      amount: Number(order.current_allocation || 0),
    })));
  },
  { immediate: true },
);

const close = () => {
  if (!props.saving) emit('close');
};

useDialogA11y({
  open: computed(() => props.open),
  dialogRef,
  initialFocusRef: closeButtonRef,
  close,
});

const toggleRow = (row: AllocationRow) => {
  row.selected = !row.selected;
  if (!row.selected) row.amount = 0;
};

const fillRows = (targetRows: AllocationRow[]) => {
  let available = Number(props.detail?.receipt_amount || 0);
  rows.forEach((row) => {
    row.amount = 0;
    row.selected = targetRows.includes(row);
  });
  targetRows.forEach((row) => {
    const amount = Math.min(Number(row.balance_due_before_receipt || 0), available);
    row.amount = Math.max(0, Math.round(amount * 100) / 100);
    row.selected = row.amount > 0;
    available = Math.max(0, Math.round((available - row.amount) * 100) / 100);
  });
};

const fillSelected = () => {
  const selectedRows = rows.filter((row) => row.selected);
  fillRows(selectedRows.length ? selectedRows : rows);
};

const fillOldestFirst = () => fillRows([...rows]);

const clear = () => {
  rows.forEach((row) => {
    row.selected = false;
    row.amount = 0;
  });
};

const save = () => {
  if (!canSave.value) return;
  emit('save', rows
    .filter((row) => row.selected && Number(row.amount || 0) > 0)
    .map((row) => ({
      order_id: row.order_id,
      amount: Math.round(Number(row.amount) * 100) / 100,
    })));
};
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[140] flex items-end justify-center bg-black/50 sm:items-center sm:p-4"
      @click.self="close"
    >
      <section
        ref="dialogRef"
        class="flex max-h-[94vh] w-full max-w-3xl flex-col overflow-hidden rounded-t-lg border border-slate-200 bg-white shadow-2xl sm:rounded-lg dark:border-slate-700 dark:bg-slate-900"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bank-receipt-allocation-title"
        tabindex="-1"
      >
        <header class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <Scale class="h-5 w-5 shrink-0 text-teal-700 dark:text-teal-300" />
              <h2 id="bank-receipt-allocation-title" class="text-base font-semibold text-slate-950 dark:text-white">
                {{ detail?.allocated_amount ? 'Переразнести поступление' : 'Распределить поступление' }}
              </h2>
            </div>
            <p v-if="detail" class="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Поступление #{{ detail.receipt_id }} · {{ money(detail.receipt_amount) }} {{ currency }}
            </p>
          </div>
          <button
            ref="closeButtonRef"
            type="button"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800"
            :disabled="saving"
            aria-label="Закрыть"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <div class="min-h-0 flex-1 overflow-y-auto p-4">
          <div v-if="loading" class="flex min-h-48 items-center justify-center gap-2 text-sm text-slate-500">
            <LoaderCircle class="h-5 w-5 animate-spin" />
            Загружаем открытые заказы
          </div>

          <template v-else-if="detail">
            <div class="mb-4 grid grid-cols-3 gap-2 text-center text-sm">
              <div class="rounded-md bg-slate-50 px-2 py-2 dark:bg-slate-800">
                <div class="text-xs text-slate-500 dark:text-slate-400">Поступило</div>
                <div class="mt-0.5 font-semibold text-slate-950 dark:text-white">{{ money(detail.receipt_amount) }}</div>
              </div>
              <div class="rounded-md bg-teal-50 px-2 py-2 dark:bg-teal-950/40">
                <div class="text-xs text-teal-700 dark:text-teal-300">Распределено</div>
                <div class="mt-0.5 font-semibold text-teal-900 dark:text-teal-100">{{ money(allocated) }}</div>
              </div>
              <div class="rounded-md bg-amber-50 px-2 py-2 dark:bg-amber-950/40">
                <div class="text-xs text-amber-700 dark:text-amber-300">Остаток</div>
                <div class="mt-0.5 font-semibold text-amber-900 dark:text-amber-100">{{ money(remainder) }}</div>
              </div>
            </div>

            <div class="mb-3 flex flex-wrap gap-2">
              <button type="button" class="btn-mini-outline" @click="fillSelected">
                <Check class="h-4 w-4" />
                По выбранным долгам
              </button>
              <button type="button" class="btn-mini-outline" @click="fillOldestFirst">
                <ListOrdered class="h-4 w-4" />
                Старые долги сначала
              </button>
              <button type="button" class="btn-mini-outline" @click="clear">
                <RotateCcw class="h-4 w-4" />
                Очистить
              </button>
            </div>

            <div v-if="rows.length" class="divide-y divide-slate-200 rounded-md border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
              <div
                v-for="row in rows"
                :key="row.order_id"
                class="grid gap-3 p-3 sm:grid-cols-[minmax(0,1fr)_10rem]"
              >
                <div class="flex min-w-0 items-start gap-3">
                  <input
                    :checked="row.selected"
                    class="mt-1 h-4 w-4 shrink-0 accent-teal-600"
                    type="checkbox"
                    :aria-label="`Выбрать заказ ${row.order_id}`"
                    @change="toggleRow(row)"
                  />
                  <div class="min-w-0">
                    <div class="font-semibold text-slate-950 dark:text-white">
                      #{{ row.order_id }} · {{ row.title || 'Заказ' }}
                    </div>
                    <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Долг до поступления: {{ money(row.balance_due_before_receipt) }} {{ currency }}
                      <span v-if="row.current_allocation">
                        · сейчас отнесено {{ money(row.current_allocation) }}
                      </span>
                    </div>
                    <div v-if="row.selected" class="mt-1 text-xs font-medium text-teal-700 dark:text-teal-300">
                      После распределения останется {{ money(Math.max(0, row.balance_due_before_receipt - Number(row.amount || 0))) }} {{ currency }}
                    </div>
                  </div>
                </div>
                <label class="text-xs font-medium text-slate-600 dark:text-slate-300">
                  Сумма
                  <div class="mt-1 flex items-center gap-2">
                    <input
                      v-model.number="row.amount"
                      class="field-input h-10 min-w-0"
                      type="number"
                      min="0"
                      step="0.01"
                      :disabled="!row.selected"
                    />
                    <span class="shrink-0 text-slate-500">{{ currency }}</span>
                  </div>
                </label>
              </div>
            </div>
            <p v-else class="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
              У плательщика нет заказов с задолженностью.
            </p>

            <p v-if="validationError || error" class="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">
              {{ validationError || error }}
            </p>
            <p v-else-if="remainder > 0" class="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              Остаток {{ money(remainder) }} {{ currency }} сохранится как нераспределённая переплата контрагента.
            </p>
          </template>
          <p v-else-if="error" class="rounded-md bg-red-50 px-3 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">
            {{ error }}
          </p>
        </div>

        <footer class="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-4 py-3 dark:border-slate-700">
          <button type="button" class="btn-mini-outline" :disabled="saving" @click="close">Отмена</button>
          <button type="button" class="btn-mini" :disabled="!canSave" @click="save">
            <LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />
            <Check v-else class="h-4 w-4" />
            {{ saving ? 'Сохраняем...' : 'Сохранить распределение' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
