<script setup lang="ts">
const props = defineProps<{ leadsCount: number }>();
const emit = defineEmits<{ navigate: [path: string] }>();

const actions = [
  { label: 'Входящие', icon: 'move_to_inbox', path: '/manager/leads' },
  { label: 'Заказы', icon: 'shopping_cart', path: '/manager/orders/kanban' },
  { label: 'Календарь', icon: 'calendar_today', path: '/manager/calendar' },
  { label: 'Каталог', icon: 'inventory_2', path: '/manager/products' },
  { label: 'Клиенты', icon: 'group', path: '/manager/customers' },
];
</script>

<template>
  <nav class="mb-5 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap lg:flex-nowrap" aria-label="Ежедневная навигация">
    <button
      v-for="action in actions"
      :key="action.path"
      type="button"
      class="relative inline-flex min-w-0 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition-colors hover:border-teal-300 hover:bg-teal-50 hover:text-teal-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-teal-800 dark:hover:bg-teal-950/30 dark:hover:text-teal-200 sm:justify-start"
      @click="emit('navigate', action.path)"
    >
      <span class="material-icons-round text-[18px] text-teal-600 dark:text-teal-400">{{ action.icon }}</span>
      <span class="truncate">{{ action.label }}</span>
      <span v-if="action.path === '/manager/leads' && props.leadsCount > 0" class="inline-flex min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 py-0.5 text-xs font-bold leading-none text-white">{{ props.leadsCount }}</span>
    </button>
  </nav>
</template>
