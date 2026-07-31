<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerOrderDetailResponse } from '../../client';
import OrderDrawerSection from './OrderDrawerSection.vue';
import { formatMoney } from './order-utils';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  expanded: boolean;
  deliveryAddress: string;
  comment: string;
}>();

const emit = defineEmits<{
  'update:expanded': [value: boolean];
  copy: [payload: { value: string | null | undefined; label: string }];
}>();

const expandedModel = computed({
  get: () => props.expanded,
  set: (value: boolean) => emit('update:expanded', value),
});

const productLines = computed(() => (
  (props.order.product_lines ?? []).map((line) => ({
    id: line.id,
    title: line.product_title || `Товар #${line.product_id}`,
    quantity: line.quantity,
    lineTotal: line.line_total,
    installationIncluded: Boolean(line.is_installation_included),
    installationPrice: Number(line.installation_price || 0),
  }))
));

const serviceLines = computed(() => (
  (props.order.service_lines ?? []).map((line) => ({
    id: line.id,
    title: line.service_title || 'Услуга',
    quantity: line.quantity,
    lineTotal: line.line_total,
  }))
));

const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const summary = computed(() => {
  const parts: string[] = [];
  const createdAt = formatDateTime(props.order.created_at);
  if (createdAt) parts.push(`создан ${createdAt}`);
  parts.push(`${productLines.value.length + serviceLines.value.length} поз.`);
  if (props.deliveryAddress) parts.push(props.deliveryAddress);
  return parts.join(' · ');
});

const copy = (value: string | null | undefined, label: string) => {
  emit('copy', { value, label });
};
</script>

<template>
  <OrderDrawerSection
    v-model:expanded="expandedModel"
    title="Входящий заказ с сайта"
    :summary="summary"
    tone="emerald"
  >
    <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700">Входящий заказ с сайта</p>
        <p class="mt-1 text-sm text-gray-500">
          <span v-if="formatDateTime(order.created_at)">Создан: {{ formatDateTime(order.created_at) }}</span>
          <span v-if="order.status" class="ml-2 inline-flex items-center rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-gray-600 ring-1 ring-gray-200">
            {{ order.status }}
          </span>
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-gray-700 shadow-sm ring-1 ring-gray-200 transition hover:bg-gray-50"
          @click="copy(order.customer?.phone, 'Телефон')"
        >
          <span class="material-icons-round text-[16px]">content_copy</span>
          Телефон
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-gray-700 shadow-sm ring-1 ring-gray-200 transition hover:bg-gray-50"
          @click="copy(deliveryAddress, 'Адрес')"
        >
          <span class="material-icons-round text-[16px]">content_copy</span>
          Адрес
        </button>
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-2">
      <div class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100">
        <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Клиент</p>
        <p class="mt-2 text-sm font-semibold text-gray-900">{{ order.customer?.full_legal_name || order.customer?.name || 'Без имени' }}</p>
        <p v-if="order.customer?.phone" class="mt-1 text-sm text-gray-700">{{ order.customer.phone }}</p>
        <p v-if="order.customer?.email" class="mt-1 text-sm text-gray-500">{{ order.customer.email }}</p>
      </div>

      <div class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100">
        <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Адрес доставки</p>
        <p class="mt-2 text-sm font-medium text-gray-900">{{ deliveryAddress || 'Адрес не указан' }}</p>
      </div>

      <div class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100 md:col-span-2">
        <div class="flex items-center justify-between gap-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Состав заказа</p>
          <span class="text-xs font-medium text-emerald-700">
            {{ productLines.length + serviceLines.length }} поз.
          </span>
        </div>
        <div class="mt-3 space-y-2">
          <div
            v-for="line in productLines"
            :key="`website-product-${line.id}`"
            class="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm font-medium text-gray-900">{{ line.title }}</p>
                <div class="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                  <span>Кол-во: {{ line.quantity }}</span>
                  <span v-if="line.installationIncluded" class="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">
                    <span class="material-icons-round text-[14px]">construction</span>
                    Монтаж включен
                    <span v-if="line.installationPrice > 0">+ {{ formatMoney(line.installationPrice) }}</span>
                  </span>
                </div>
              </div>
              <span class="whitespace-nowrap text-sm font-semibold text-gray-800">{{ formatMoney(line.lineTotal) }}</span>
            </div>
          </div>

          <div
            v-for="line in serviceLines"
            :key="`website-service-${line.id}`"
            class="flex items-start justify-between gap-3 rounded-xl border border-gray-100 bg-gray-50 px-3 py-2"
          >
            <div>
              <p class="text-sm font-medium text-gray-900">{{ line.title }}</p>
              <p class="mt-1 text-xs text-gray-500">Кол-во: {{ line.quantity }}</p>
            </div>
            <span class="whitespace-nowrap text-sm font-semibold text-gray-800">{{ formatMoney(line.lineTotal) }}</span>
          </div>

          <p
            v-if="!productLines.length && !serviceLines.length"
            class="rounded-xl border border-dashed border-gray-200 px-3 py-4 text-sm text-gray-500"
          >
            Позиции заказа отсутствуют.
          </p>
        </div>
      </div>

      <div v-if="comment.trim()" class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100 md:col-span-2">
        <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Комментарий клиента</p>
        <p class="mt-2 whitespace-pre-line text-sm text-gray-800">{{ comment }}</p>
      </div>
    </div>
  </OrderDrawerSection>
</template>
