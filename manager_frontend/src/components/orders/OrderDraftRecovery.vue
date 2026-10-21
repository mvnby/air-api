<script setup lang="ts">
import type { DraftConflict } from './order-draft-merge';
defineProps<{ conflicts: DraftConflict[] }>();
defineEmits<{ resolve: [id: string, choice: 'local' | 'server'] }>();
const labels: Record<string, string> = {
  form: '', title: 'Название', comment: 'Комментарий', status: 'Статус', workflowType: 'Тип заказа', repairMeta: 'Данные ремонта',
  managerLabels: 'Метки', nextFollowupDate: 'Следующий контакт', assessmentDate: 'Дата замера', installationDate: 'Дата монтажа',
  installerId: 'Исполнитель', customerDeliveryAddress: 'Адрес объекта', customerBranchId: 'Объект клиента',
  measurementRequired: 'Нужен замер', measurerId: 'Замерщик', measurementResult: 'Результат замера', additionalConditions: 'Условия',
  negotiationStatus: 'Этап переговоров', executionStatus: 'Этап работ', executionWithoutPayment: 'Работы без оплаты',
  executionWithoutPaymentReason: 'Причина работ без оплаты', autoExecutionOnPayment: 'Начало работ после оплаты', autoCloseOnPayment: 'Завершение после оплаты',
  enableCurrency: 'Валютная сделка', targetCurrency: 'Валюта', targetCurrencyAmount: 'Сумма в валюте',
  additions: 'Возможно, уже сохранённые позиции', currency: 'Валюта и сумма', products: 'Товары', services: 'Услуги', price: 'Цена', cost: 'Себестоимость', quantity: 'Количество', description: 'Описание',
  client_description: 'Описание для клиента', product_id: 'Товар', product_query: 'Название товара', service_id: 'Услуга', logistics_components: 'Логистика',
};
const label = (conflict: DraftConflict) => conflict.path.map(part => labels[part] ?? (/^\d+$/.test(part) ? `Позиция №${part}` : part.replace(/_/g, ' '))).filter(Boolean).join(' · ');
const display = (value: unknown): string => {
  if (value === undefined) return 'Удалено';
  if (value === null || value === '') return 'Не заполнено';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (Array.isArray(value)) return value.length ? value.map(display).join('\n') : 'Нет позиций';
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${labels[key] || key.replace(/_/g, ' ')}: ${display(item)}`).join('\n');
  return String(value);
};
</script>

<template>
  <section aria-label="Восстановление черновика" class="my-3 min-w-0 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-slate-900" role="alert">
    <h2 class="font-semibold">Проверьте восстановленный черновик</h2>
    <p class="mt-1">Сохранение приостановлено до выбора значений. Обе версии черновика сохранены в этом браузере.</p>
    <p v-if="conflicts.some(item => item.legacy)" class="mt-1">В старом черновике нет исходной версии. Проверьте каждое отличие перед восстановлением. Для черновика без сведений об авторе также убедитесь, что это ваши данные.</p>
    <p v-else class="mt-1">Эти значения изменились и в черновике, и на сервере. Остальные правки восстановлены с учётом актуальных данных.</p>
    <article v-for="conflict in conflicts" :key="conflict.id" class="mt-3 min-w-0 rounded-lg border border-amber-200 bg-white p-3">
      <h3 class="font-semibold">{{ label(conflict) }}</h3>
      <div class="mt-2 grid min-w-0 gap-3 sm:grid-cols-2">
        <div class="min-w-0"><p class="font-medium">Мой черновик</p><p class="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{{ display(conflict.local) }}</p><button type="button" class="mt-2 min-h-10 rounded-lg border border-slate-300 px-3 font-semibold" @click="$emit('resolve', conflict.id, 'local')">Использовать черновик</button></div>
        <div class="min-w-0"><p class="font-medium">Сейчас на сервере</p><p class="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{{ display(conflict.server) }}</p><button type="button" class="mt-2 min-h-10 rounded-lg border border-slate-300 px-3 font-semibold" @click="$emit('resolve', conflict.id, 'server')">Оставить серверное</button></div>
      </div>
    </article>
  </section>
</template>
