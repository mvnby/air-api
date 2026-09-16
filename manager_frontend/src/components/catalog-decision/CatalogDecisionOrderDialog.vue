<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useDialogA11y } from '../../composables/useDialogA11y';
import {
  ManagerCatalogDecisionService,
  ManagerOrdersService,
  type ManagerOrderDetailResponse,
  type ManagerOrderListItemResponse,
} from '../../client';
import type { CatalogDecisionSelectionItem } from '../../services/catalog-decision-selection';
import {
  defaultCatalogDecisionAttachMode,
  hasActiveOrderProducts,
  type CatalogDecisionAttachMode,
} from '../../services/catalog-decision-order';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ open: boolean; items: CatalogDecisionSelectionItem[] }>();
const emit = defineEmits<{ close: []; attached: [orderId: number] }>();
const orders = ref<ManagerOrderListItemResponse[]>([]);
const search = ref('');
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const selectedOrder = ref<ManagerOrderDetailResponse | null>(null);
const mode = ref<CatalogDecisionAttachMode>('auto');
const proposalMode = ref<'bundle' | 'alternatives'>('alternatives');
const dialogRef = ref<HTMLElement | null>(null);
const close = () => { if (!saving.value) emit('close'); };
useDialogA11y({ open: computed(() => props.open), dialogRef, close });
let requestGeneration = 0;
let detailGeneration = 0;
const choosing = ref(false);
onBeforeUnmount(() => { clearTimeout(searchTimer); requestGeneration += 1; detailGeneration += 1; });
let searchTimer: ReturnType<typeof setTimeout> | undefined;

const hasProducts = computed(() => hasActiveOrderProducts(selectedOrder.value));
const orderLabel = (order: ManagerOrderListItemResponse) => order.title?.trim() || order.customer?.name || `Заказ #${order.id}`;

const loadOrders = async () => {
  const generation = ++requestGeneration;
  loading.value = true;
  error.value = '';
  try {
    const response = await ManagerOrdersService.getManagerOrders('all', 1, 10, 'negotiation', search.value.trim() || undefined, false, 'updated_at_desc');
    if (generation !== requestGeneration) return;
    orders.value = response.items || [];
  } catch (err) {
    if (generation === requestGeneration) error.value = getApiErrorMessage(err) || 'Не удалось загрузить заказы';
  } finally {
    if (generation === requestGeneration) loading.value = false;
  }
};

watch(() => props.open, (open) => {
  if (!open) { clearTimeout(searchTimer); requestGeneration += 1; detailGeneration += 1; return; }
  search.value = '';
  selectedOrder.value = null;
  mode.value = 'auto';
  proposalMode.value = props.items.length > 1 ? 'alternatives' : 'bundle';
  void loadOrders();
}, { immediate: true });
watch(search, () => {
  if (!props.open) return;
  clearTimeout(searchTimer);
  requestGeneration += 1;
  searchTimer = setTimeout(() => void loadOrders(), 250);
});

const chooseOrder = async (order: ManagerOrderListItemResponse) => {
  if (saving.value) return;
  error.value = '';
  const generation = ++detailGeneration;
  selectedOrder.value = null; choosing.value = true;
  try {
    const detail = await ManagerOrdersService.getManagerOrderDetail(order.id);
    if (generation !== detailGeneration) return;
    selectedOrder.value = detail;
    mode.value = defaultCatalogDecisionAttachMode(selectedOrder.value);
  } catch (err) {
    if (generation === detailGeneration) error.value = getApiErrorMessage(err) || 'Не удалось открыть заказ';
  } finally { if (generation === detailGeneration) choosing.value = false; }
};

const submit = async () => {
  if (!selectedOrder.value || saving.value) return;
  const orderId = selectedOrder.value.id;
  saving.value = true;
  error.value = '';
  try {
    await ManagerCatalogDecisionService.attachManagerCatalogDecisionToOrder(orderId, {
      product_ids: props.items.map(item => item.id),
      mode: proposalMode.value === 'alternatives' ? 'new_alternative' : (hasProducts.value ? mode.value : 'auto'),
      proposal_mode: proposalMode.value,
    });
    emit('attached', orderId);
  } catch (err) {
    error.value = getApiErrorMessage(err) || 'Не удалось прикрепить модели к заказу';
    try {
      selectedOrder.value = await ManagerOrdersService.getManagerOrderDetail(orderId);
      if (hasProducts.value && mode.value === 'auto') mode.value = 'new_alternative';
    } catch { /* Keep the actionable mutation error visible. */ }
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4" @click.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="attach-order-title" tabindex="-1" class="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-xl sm:rounded-2xl">
        <div class="flex items-start justify-between gap-4"><div><h2 id="attach-order-title" class="text-lg font-bold text-gray-900">Прикрепить к заказу</h2><p class="mt-1 text-sm text-gray-500">Выберите заказ в переговорах.</p></div><button type="button" class="material-icons-round text-gray-400" aria-label="Закрыть" @click="close">close</button></div>
        <input v-model="search" :disabled="saving" aria-label="Номер заказа, клиент или телефон" class="mt-4 w-full rounded-xl border border-gray-300 px-3 py-2.5 outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100" placeholder="Номер заказа, клиент или телефон" inputmode="search" />
        <div class="mt-3 max-h-48 min-h-28 overflow-y-auto rounded-xl border border-gray-200">
          <p v-if="loading" class="p-4 text-center text-sm text-gray-500">Загрузка…</p>
          <p v-else-if="!orders.length" class="p-4 text-center text-sm text-gray-500">Подходящих заказов не найдено.</p>
          <template v-else><button v-for="order in orders" :key="order.id" type="button" class="flex w-full items-center gap-3 border-b border-gray-100 px-3 py-3 text-left last:border-0" :class="selectedOrder?.id === order.id ? 'bg-brand-50' : 'hover:bg-gray-50'" :disabled="saving" @click="chooseOrder(order)"><span class="font-semibold text-brand-700">#{{ order.id }}</span><span class="min-w-0 flex-1"><span class="block truncate text-sm font-medium text-gray-900">{{ orderLabel(order) }}</span><span class="block truncate text-xs text-gray-500">{{ order.customer?.phone || 'Телефон не указан' }}</span></span><span v-if="selectedOrder?.id === order.id" class="material-icons-round text-brand-600">check_circle</span></button></template>
        </div>
        <fieldset v-if="items.length > 1" class="mt-4">
          <legend class="text-sm font-medium text-gray-800">Как предложить модели клиенту?</legend>
          <div class="mt-2 grid grid-cols-2 gap-2">
            <button v-for="kind in (['alternatives', 'bundle'] as const)" :key="kind" type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="proposalMode === kind ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 text-gray-700'" :aria-pressed="proposalMode === kind" :disabled="saving" @click="proposalMode = kind">{{ kind === 'alternatives' ? 'Альтернативы' : 'Один комплект' }}</button>
          </div>
        </fieldset>
        <p v-if="choosing" role="status" class="mt-2 text-sm text-gray-500">Загружаем заказ…</p>
        <div v-if="selectedOrder" class="mt-4 rounded-xl bg-gray-50 p-3">
          <p v-if="proposalMode === 'alternatives'" class="text-sm text-gray-700">Каждая модель — отдельный вариант. Заполненные предложения сохранятся; пустое основное может принять первую модель.</p>
          <p v-else-if="!hasProducts" class="text-sm text-gray-700">В заказе ещё нет оборудования — модели будут добавлены в основное предложение.</p>
          <div v-else><p class="text-sm font-medium text-gray-800">В заказе уже есть товары. Как поступить?</p><div class="mt-2 grid grid-cols-2 gap-2"><button type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="mode === 'new_alternative' ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 bg-white text-gray-700'" :disabled="saving" @click="mode = 'new_alternative'">Новый вариант</button><button type="button" class="rounded-xl border px-3 py-2.5 text-sm font-semibold" :class="mode === 'replace_selected' ? 'border-amber-500 bg-amber-50 text-amber-800' : 'border-gray-200 bg-white text-gray-700'" :disabled="saving" @click="mode = 'replace_selected'">Заменить основное</button></div><p class="mt-2 text-xs text-gray-500">{{ mode === 'replace_selected' ? 'Товары основного предложения будут заменены выбранным комплектом.' : 'Существующее предложение останется без изменений.' }}</p></div>
        </div>
        <p v-if="error" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
        <div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded-xl px-4 py-2.5 text-sm font-semibold text-gray-600" @click="close">Отмена</button><button type="button" class="rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" :disabled="!selectedOrder || saving || choosing" @click="submit">{{ saving ? 'Сохраняем…' : 'Прикрепить' }}</button></div>
      </section>
    </div>
  </Teleport>
</template>
