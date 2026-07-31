<script setup lang="ts">
import { computed, ref } from 'vue';
import type { ManagerOrderDetailResponse } from '../../client';
import type { ProductLine } from './order-editor-types';
import OrderDocumentsPanel from './OrderDocumentsPanel.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';

type BeforeGenerateResult = boolean | void | { proceed?: boolean; mutated?: boolean };

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  activeProposalId?: number | null;
  productLines: ProductLine[];
  total: number;
  beforeGenerate?: (type: string) => BeforeGenerateResult | Promise<BeforeGenerateResult>;
}>();

const emit = defineEmits<{
  refresh: [];
  toast: [payload: { message: string; type?: 'success' | 'error' }];
}>();

const expanded = defineModel<boolean>('expanded', { required: true });
const panelRef = ref<InstanceType<typeof OrderDocumentsPanel> | null>(null);

const documents = computed(() => props.order.documents || []);
const isCompanyOrder = computed(() => props.order.customer?.type === 'company' || Boolean(props.order.customer?.inn));
const hasOrderContract = computed(() => documents.value.some((document) => document.doc_type === 'contract'));
const hasContract = computed(() => (
  (isCompanyOrder.value ? Boolean(props.order.customer_contract_id) : false) || hasOrderContract.value
));
const hasInvoice = computed(() => documents.value.some((document) => document.doc_type === 'invoice'));
const hasClosingBaseDocument = computed(() => hasContract.value || hasInvoice.value);
const summary = computed(() => {
  const count = documents.value.length;
  if (!count) return 'Документов нет';
  const mod100 = count % 100;
  const mod10 = count % 10;
  const noun = mod100 >= 11 && mod100 <= 14
    ? 'документов'
    : mod10 === 1
      ? 'документ'
      : mod10 >= 2 && mod10 <= 4
        ? 'документа'
        : 'документов';
  return `${count} ${noun}${hasContract.value ? '' : ' · договор не создан'}`;
});
const hasError = computed(() => (
  isCompanyOrder.value && !props.order.customer_contract_id && !hasClosingBaseDocument.value
));
const customerPhoneDigits = computed(() => String(props.order.customer?.phone || '').replace(/\D/g, ''));
const whatsappUrl = computed(() => {
  const name = props.order.customer?.name || '';
  const total = Number(props.total || 0).toLocaleString('ru-RU');
  const message = `Здравствуйте, ${name}! Расчет по вашему заказу: Итого к оплате ${total} BYN. Подтверждаем?`;
  return `https://wa.me/${customerPhoneDigits.value}?text=${encodeURIComponent(message)}`;
});
const viberUrl = computed(() => `viber://chat?number=%2B${customerPhoneDigits.value}`);

const openSend = () => panelRef.value?.openSend();
const openCreate = () => panelRef.value?.openCreate();

defineExpose({ openSend, openCreate });
</script>

<template>
  <OrderDrawerSection
    id="order-workspace-documents"
    v-model:expanded="expanded"
    title="Документы"
    :summary="summary"
    tone="amber"
    :has-error="hasError"
  >
    <div v-if="order.status === 'negotiation' && order.customer?.type === 'individual'" class="mb-6">
      <div class="flex flex-wrap gap-2">
        <a :href="whatsappUrl" target="_blank" class="flex items-center gap-1 rounded-xl bg-[#25D366] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#20BE5A]">
          <span class="material-icons-round text-[18px]">chat</span> Отправить в WhatsApp
        </a>
        <a :href="viberUrl" target="_blank" class="flex items-center gap-1 rounded-xl bg-[#7360f2] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#5e4cd1]">
          <span class="material-icons-round text-[18px]">chat</span> Viber
        </a>
      </div>
    </div>

    <OrderDocumentsPanel
      ref="panelRef"
      :order="order"
      :active-proposal-id="activeProposalId"
      :product-lines="productLines"
      :before-generate="beforeGenerate"
      @refresh="emit('refresh')"
      @toast="emit('toast', $event)"
    />
  </OrderDrawerSection>
</template>
