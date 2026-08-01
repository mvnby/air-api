<script setup lang="ts">
import type { ManagerOrderImportPreviewResponse } from '../../client';

defineProps<{
  preview: ManagerOrderImportPreviewResponse;
  filename: string;
  loading: boolean;
}>();

defineEmits<{
  cancel: [];
  commit: [];
}>();
</script>

<template>
  <div class="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
    <div class="w-full max-w-2xl rounded-[1.5rem] border border-gray-200 bg-white p-5 text-gray-700 shadow-2xl">
      <div class="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">Импорт заказов</h2>
          <p class="mt-1 text-sm text-gray-500">{{ filename || 'orders-export.json' }}</p>
        </div>
        <button class="btn-mini-outline" type="button" @click="$emit('cancel')">Закрыть</button>
      </div>

      <div class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-xl border border-gray-100 bg-slate-50 p-3">
          <p class="text-xs text-gray-500">Заказы</p>
          <p class="text-xl font-bold text-gray-900">{{ preview.orders_count }}</p>
        </div>
        <div class="rounded-xl border border-gray-100 bg-slate-50 p-3">
          <p class="text-xs text-gray-500">Товары найдены</p>
          <p class="text-xl font-bold text-teal-700">
            {{ preview.products_matched }} / {{ preview.products_total }}
          </p>
        </div>
        <div class="rounded-xl border border-gray-100 bg-slate-50 p-3">
          <p class="text-xs text-gray-500">Новые клиенты</p>
          <p class="text-xl font-bold text-gray-900">
            {{ preview.customers?.filter((item) => item.status === 'will_create').length || 0 }}
          </p>
        </div>
      </div>

      <div
        v-if="preview.warnings?.length"
        class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
      >
        <p v-for="warning in preview.warnings" :key="warning">{{ warning }}</p>
      </div>

      <div v-if="preview.products_missing" class="mt-4 max-h-56 overflow-auto rounded-xl border border-red-100">
        <table class="w-full text-left text-sm">
          <thead class="bg-red-50 text-xs uppercase text-red-700">
            <tr><th class="px-3 py-2">Товар</th><th class="px-3 py-2">Причина</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="item in preview.products?.filter((product) => product.status !== 'matched')"
              :key="`${item.source_order_id}-${item.product_title}`"
              class="border-t border-red-100"
            >
              <td class="px-3 py-2">{{ item.product_title }}</td>
              <td class="px-3 py-2 text-red-700">{{ item.reason || 'not_found' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button class="btn-mini-outline justify-center" type="button" :disabled="loading" @click="$emit('cancel')">
          Отмена
        </button>
        <button class="btn-mini justify-center" type="button" :disabled="loading || !preview.can_import" @click="$emit('commit')">
          {{ loading ? 'Импорт...' : 'Создать заказы' }}
        </button>
      </div>
    </div>
  </div>
</template>
