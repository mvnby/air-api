<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ManagerEquipmentLinksService, type ManagerOrderDetailResponse, type ManagerOrderEquipmentLinkItemResponse } from '../../../client';

const props = defineProps<{ order: ManagerOrderDetailResponse; proposalId: number | null }>();
const selected = defineModel<number | null>({ required: true });
const links = ref<ManagerOrderEquipmentLinkItemResponse[]>([]);
const loading = ref(false);
const failed = ref(false);
const retry = ref(0);
const choices = computed(() => {
  const proposal = props.order.proposals?.find(item => item.id === props.proposalId);
  const productIds = proposal?.product_lines?.map(line => line.product_id) || [];
  const multipleProposals = (props.order.proposals || []).filter(item => !item.is_archived).length > 1;
  const choices = new Map<number, string>();
  for (const { role, equipment } of links.value) {
    if (equipment.is_archived || equipment.warranty_mode === 'none' || equipment.customer_id !== props.order.customer?.id) continue;
    if (role !== 'sale' || ['installed_by_us', 'customer_owned'].includes(equipment.equipment_source || '')) continue;
    if (equipment.customer_branch_id && props.order.customer_branch?.id && equipment.customer_branch_id !== props.order.customer_branch.id) continue;
    if (proposal && (equipment.catalog_product_id ? !productIds.includes(equipment.catalog_product_id) : multipleProposals)) continue;
    const title = equipment.display_name || [equipment.brand, equipment.model].filter(Boolean).join(' ') || `Оборудование № ${equipment.id}`;
    choices.set(equipment.id, title + (equipment.serial ? ' · ' + equipment.serial : '') + (equipment.location_hint ? ' · ' + equipment.location_hint : ''));
  }
  return choices;
});
watch([() => props.order.id, () => props.order.customer?.id, retry], async ([orderId], _old, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  links.value = [];
  loading.value = true;
  failed.value = false;
  try {
    const response = await ManagerEquipmentLinksService.listManagerOrderEquipmentLinks(Number(orderId));
    if (current) links.value = response.items || [];
  } catch {
    if (current) failed.value = true;
  } finally {
    if (current) loading.value = false;
  }
}, { immediate: true });
watch([choices, loading], () => {
  if (!loading.value && selected.value && !choices.value.has(selected.value)) selected.value = null;
});
</script>

<template>
  <div class="mt-4 min-w-0" data-testid="warranty-equipment-picker">
    <label class="block text-sm font-semibold">
      Оборудование
      <select v-model="selected" class="mt-1 block h-10 w-full min-w-0 max-w-full rounded-lg border border-slate-300 bg-white px-2 text-sm dark:border-slate-600 dark:bg-slate-900" :disabled="loading || failed || !choices.size" data-testid="warranty-equipment">
        <option :value="null">{{ loading ? 'Загрузка…' : 'Выберите оборудование из продажи' }}</option>
        <option v-for="[id, title] in choices" :key="id" :value="id">{{ title }}</option>
      </select>
    </label>
    <p v-if="failed" role="status" class="mt-1 text-sm">Не удалось загрузить оборудование. <button type="button" class="font-semibold underline" @click="retry++">Повторить</button></p>
    <p v-else-if="!loading && !choices.size" class="mt-1 text-sm text-slate-600 dark:text-slate-300">Добавьте оборудование продажи и укажите гарантию в разделе «Оборудование» заказа.</p>
    <p v-else-if="selected" class="mt-1 break-words text-xs text-slate-600 dark:text-slate-300" data-testid="warranty-equipment-details">{{ choices.get(selected) }}</p>
  </div>
</template>
