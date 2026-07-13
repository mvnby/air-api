<script setup lang="ts">
import { MapPin, Phone, UserRound, Wrench } from 'lucide-vue-next';
import EquipmentAttentionBadges from './EquipmentAttentionBadges.vue';
import {
  equipmentIdentifiers,
  equipmentLocation,
  equipmentSubtitle,
  equipmentTitle,
  formatEquipmentDate,
  hasDistinctServiceContact,
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
  <div class="grid gap-3 lg:hidden">
    <article
      v-for="item in items"
      :key="item.id"
      class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800"
    >
      <div class="min-w-0">
        <p class="break-words text-base font-semibold leading-snug text-gray-950 dark:text-white">{{ equipmentTitle(item) }}</p>
        <p v-if="equipmentSubtitle(item)" class="mt-1 break-words text-xs text-gray-500 dark:text-slate-400">
          {{ equipmentSubtitle(item) }}
        </p>
        <p v-if="equipmentIdentifiers(item)" class="mt-1 break-words text-xs font-medium text-gray-500 dark:text-slate-400">
          {{ equipmentIdentifiers(item) }}
        </p>
      </div>

      <div class="mt-3">
        <EquipmentAttentionBadges :reasons="item.attention_reasons" />
      </div>

      <div class="mt-4 space-y-2.5 border-t border-gray-100 pt-3 text-sm dark:border-slate-700">
        <div class="flex items-start gap-2.5">
          <UserRound class="mt-0.5 h-4 w-4 shrink-0 text-gray-400 dark:text-slate-500" />
          <div class="min-w-0">
            <p class="break-words font-semibold text-gray-900 dark:text-slate-100">
              {{ item.customer_name || `Клиент #${item.customer_id}` }}
            </p>
            <a
              v-if="item.customer_phone"
              class="mt-0.5 block w-fit text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
              :href="phoneHref(item.customer_phone)"
            >
              {{ item.customer_phone }}
            </a>
          </div>
        </div>

        <div v-if="equipmentLocation(item)" class="flex items-start gap-2.5">
          <MapPin class="mt-0.5 h-4 w-4 shrink-0 text-gray-400 dark:text-slate-500" />
          <p class="min-w-0 break-words text-gray-600 dark:text-slate-300">{{ equipmentLocation(item) }}</p>
        </div>

        <div v-if="hasDistinctServiceContact(item)" class="flex items-start gap-2.5">
          <Phone class="mt-0.5 h-4 w-4 shrink-0 text-gray-400 dark:text-slate-500" />
          <div class="min-w-0">
            <p class="break-words text-gray-600 dark:text-slate-300">{{ serviceContactName(item) || 'Контакт по сервису' }}</p>
            <a
              v-if="serviceContactPhone(item)"
              class="mt-0.5 block w-fit text-xs font-medium text-teal-700 hover:underline dark:text-teal-300"
              :href="phoneHref(serviceContactPhone(item))"
            >
              {{ serviceContactPhone(item) }}
            </a>
          </div>
        </div>
      </div>

      <dl class="mt-4 grid grid-cols-3 divide-x divide-gray-200 border-y border-gray-200 py-3 text-center dark:divide-slate-700 dark:border-slate-700">
        <div class="min-w-0 px-1.5">
          <dt class="text-[11px] font-medium leading-tight text-gray-500 dark:text-slate-400">Последнее ТО</dt>
          <dd class="mt-1 break-words text-xs font-semibold text-gray-800 dark:text-slate-200">{{ formatEquipmentDate(item.last_service_at) }}</dd>
        </div>
        <div class="min-w-0 px-1.5">
          <dt class="text-[11px] font-medium leading-tight text-gray-500 dark:text-slate-400">Следующее ТО</dt>
          <dd class="mt-1 break-words text-xs font-semibold" :class="maintenanceDateClass(item)">
            {{ formatEquipmentDate(item.next_maintenance_due_at) }}
          </dd>
        </div>
        <div class="min-w-0 px-1.5">
          <dt class="text-[11px] font-medium leading-tight text-gray-500 dark:text-slate-400">Гарантия до</dt>
          <dd class="mt-1 break-words text-xs font-semibold" :class="warrantyDateClass(item)">
            {{ formatEquipmentDate(item.warranty_expires_at) }}
          </dd>
        </div>
      </dl>

      <button
        type="button"
        class="mt-4 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-md bg-teal-600 px-3 py-2 text-sm font-semibold leading-tight text-white transition hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 dark:ring-offset-slate-800"
        @click="emit('createMaintenanceOrder', item)"
      >
        <Wrench class="h-4 w-4 shrink-0" />
        Создать заказ на ТО
      </button>
    </article>
  </div>
</template>
