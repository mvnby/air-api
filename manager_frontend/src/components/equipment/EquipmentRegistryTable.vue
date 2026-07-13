<script setup lang="ts">
import { Wrench } from 'lucide-vue-next';
import EquipmentAttentionBadges from './EquipmentAttentionBadges.vue';
import {
  equipmentIdentifiers,
  equipmentLocation,
  equipmentSubtitle,
  equipmentTitle,
  formatEquipmentDate,
  maintenanceDateClass,
  phoneHref,
  serviceContactName,
  serviceContactPhone,
  warrantyDateClass,
} from './registry';
import type { EquipmentRegistryItem } from './types';

defineProps<{
  items: EquipmentRegistryItem[];
}>();

const emit = defineEmits<{
  createMaintenanceOrder: [item: EquipmentRegistryItem];
}>();
</script>

<template>
  <div class="hidden overflow-x-auto border-y border-gray-200 dark:border-slate-700 lg:block">
    <table class="w-full min-w-[1120px] table-fixed border-collapse">
      <colgroup>
        <col class="w-[21%]">
        <col class="w-[18%]">
        <col class="w-[14%]">
        <col class="w-[19%]">
        <col class="w-[14%]">
        <col class="w-[14%]">
      </colgroup>
      <thead class="bg-gray-50 text-left text-xs font-semibold text-gray-500 dark:bg-slate-900/60 dark:text-slate-400">
        <tr>
          <th class="px-4 py-2.5">Оборудование</th>
          <th class="px-4 py-2.5">Клиент и объект</th>
          <th class="px-4 py-2.5">Контакт по сервису</th>
          <th class="px-4 py-2.5">Контрольные даты</th>
          <th class="px-4 py-2.5">Статус</th>
          <th class="px-4 py-2.5 text-right">Действие</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-200 bg-white dark:divide-slate-700 dark:bg-slate-800">
        <tr v-for="item in items" :key="item.id" class="align-top transition hover:bg-gray-50 dark:hover:bg-slate-700/50">
          <td class="px-4 py-3">
            <p class="break-words text-sm font-semibold text-gray-950 dark:text-white">{{ equipmentTitle(item) }}</p>
            <p v-if="equipmentSubtitle(item)" class="mt-0.5 break-words text-xs text-gray-500 dark:text-slate-400">
              {{ equipmentSubtitle(item) }}
            </p>
            <p v-if="equipmentIdentifiers(item)" class="mt-1 break-words text-xs font-medium text-gray-500 dark:text-slate-400">
              {{ equipmentIdentifiers(item) }}
            </p>
          </td>

          <td class="px-4 py-3">
            <p class="break-words text-sm font-semibold text-gray-900 dark:text-slate-100">
              {{ item.customer_name || `Клиент #${item.customer_id}` }}
            </p>
            <a
              v-if="item.customer_phone"
              class="mt-0.5 block w-fit text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
              :href="phoneHref(item.customer_phone)"
            >
              {{ item.customer_phone }}
            </a>
            <p v-if="equipmentLocation(item)" class="mt-1.5 break-words text-xs leading-5 text-gray-500 dark:text-slate-400">
              {{ equipmentLocation(item) }}
            </p>
          </td>

          <td class="px-4 py-3">
            <p class="break-words text-sm font-medium text-gray-900 dark:text-slate-100">
              {{ serviceContactName(item) || '—' }}
            </p>
            <a
              v-if="serviceContactPhone(item)"
              class="mt-0.5 block w-fit text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
              :href="phoneHref(serviceContactPhone(item))"
            >
              {{ serviceContactPhone(item) }}
            </a>
          </td>

          <td class="px-4 py-3">
            <dl class="space-y-1.5 text-xs">
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-gray-500 dark:text-slate-400">Последнее ТО</dt>
                <dd class="shrink-0 font-semibold text-gray-800 dark:text-slate-200">{{ formatEquipmentDate(item.last_service_at) }}</dd>
              </div>
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-gray-500 dark:text-slate-400">Следующее ТО</dt>
                <dd class="shrink-0 font-semibold" :class="maintenanceDateClass(item)">
                  {{ formatEquipmentDate(item.next_maintenance_due_at) }}
                </dd>
              </div>
              <div class="flex items-baseline justify-between gap-3">
                <dt class="text-gray-500 dark:text-slate-400">Гарантия до</dt>
                <dd class="shrink-0 font-semibold" :class="warrantyDateClass(item)">
                  {{ formatEquipmentDate(item.warranty_expires_at) }}
                </dd>
              </div>
            </dl>
          </td>

          <td class="px-4 py-3">
            <EquipmentAttentionBadges :reasons="item.attention_reasons" />
          </td>

          <td class="px-4 py-3 text-right">
            <button
              type="button"
              class="ml-auto inline-flex min-h-9 w-full items-center justify-center gap-1.5 rounded-md bg-teal-600 px-2.5 py-1.5 text-xs font-semibold leading-tight text-white transition hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 dark:ring-offset-slate-800"
              @click="emit('createMaintenanceOrder', item)"
            >
              <Wrench class="h-3.5 w-3.5 shrink-0" />
              Создать заказ на ТО
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
