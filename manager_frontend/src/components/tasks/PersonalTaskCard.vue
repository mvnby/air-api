<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Bell, CalendarClock, ChevronDown, ChevronUp, RotateCcw, Save, X } from 'lucide-vue-next';

import type { PersonalTask, PersonalTaskAssignee, PersonalTaskUpdate } from '../../services/personal-tasks-api';

const props = defineProps<{
  task: PersonalTask;
  staff: PersonalTaskAssignee[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  toggle: [task: PersonalTask];
  cancel: [task: PersonalTask];
  save: [task: PersonalTask, payload: PersonalTaskUpdate];
}>();

const editing = ref(false);
const text = ref('');
const description = ref('');
const assignee = ref('');
const dueAt = ref('');
const reminderAt = ref('');
const leadId = ref('');
const customerId = ref('');
const orderId = ref('');
const equipmentId = ref('');

const toLocalInput = (value?: string | null): string => {
  if (!value) return '';
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};

const reset = () => {
  text.value = props.task.text;
  description.value = props.task.description || '';
  assignee.value = props.task.assignee_staff_user_id ? String(props.task.assignee_staff_user_id) : '';
  dueAt.value = toLocalInput(props.task.due_at);
  reminderAt.value = toLocalInput(props.task.reminder_at);
  leadId.value = props.task.lead_id ? String(props.task.lead_id) : '';
  customerId.value = props.task.customer_id ? String(props.task.customer_id) : '';
  orderId.value = props.task.order_id ? String(props.task.order_id) : '';
  equipmentId.value = props.task.equipment_id ? String(props.task.equipment_id) : '';
};

watch(() => props.task, reset, { immediate: true, deep: true });
watch(() => props.task.version, () => { editing.value = false; });

const formatDate = (value?: string | null) => value
  ? new Intl.DateTimeFormat('ru-BY', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
  : '';

const dueLabel = computed(() => props.task.due_at ? formatDate(props.task.due_at) : 'Без срока');

const optionalId = (value: string): number | null => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
};

const save = () => {
  if (!text.value.trim()) return;
  emit('save', props.task, {
    expected_version: props.task.version,
    text: text.value.trim(),
    description: description.value.trim() || null,
    assignee_staff_user_id: optionalId(assignee.value),
    due_at: dueAt.value ? new Date(dueAt.value).toISOString() : null,
    reminder_at: reminderAt.value ? new Date(reminderAt.value).toISOString() : null,
    lead_id: optionalId(leadId.value),
    customer_id: optionalId(customerId.value),
    order_id: optionalId(orderId.value),
    equipment_id: optionalId(equipmentId.value),
  });
};
</script>

<template>
  <article class="rounded-xl border bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900" :class="task.reminder_due ? 'border-amber-300 dark:border-amber-500/60' : 'border-slate-200'">
    <div class="flex items-start gap-3">
      <button
        type="button"
        :data-testid="`personal-task-toggle-${task.id}`"
        class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 transition disabled:opacity-50"
        :class="task.status === 'completed' ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-slate-300 bg-white dark:bg-slate-900'"
        :disabled="busy"
        :aria-label="task.status === 'active' ? 'Завершить поручение' : 'Вернуть поручение'"
        @click="emit('toggle', task)"
      >
        <span v-if="task.status === 'completed'" aria-hidden="true">✓</span>
        <RotateCcw v-else-if="task.status === 'cancelled'" class="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      <div class="min-w-0 flex-1">
        <p class="break-words font-medium text-slate-900 dark:text-white" :class="task.status !== 'active' ? 'line-through opacity-70' : ''">{{ task.text }}</p>
        <p v-if="task.description" class="mt-1 whitespace-pre-line text-sm text-slate-600 dark:text-slate-300">{{ task.description }}</p>
        <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          <span class="inline-flex items-center gap-1"><CalendarClock class="h-3.5 w-3.5" />{{ dueLabel }}</span>
          <span v-if="task.reminder_at" class="inline-flex items-center gap-1" :class="task.reminder_due ? 'font-semibold text-amber-700 dark:text-amber-300' : ''"><Bell class="h-3.5 w-3.5" />{{ formatDate(task.reminder_at) }}</span>
          <span v-if="task.assignee_name">Исполнитель: {{ task.assignee_name }}</span>
          <a v-if="task.order_id" class="text-brand-700 hover:underline dark:text-brand-300" :href="`/manager/orders/kanban?orderId=${task.order_id}`">Заказ #{{ task.order_id }}</a>
          <a v-if="task.customer_id" class="text-brand-700 hover:underline dark:text-brand-300" :href="`/manager/customers/profile?customerId=${task.customer_id}`">Клиент #{{ task.customer_id }}</a>
          <a v-if="task.lead_id" class="text-brand-700 hover:underline dark:text-brand-300" href="/manager/leads">Входящее #{{ task.lead_id }}</a>
        </div>
      </div>
      <button type="button" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" :aria-label="editing ? 'Закрыть редактирование' : 'Редактировать поручение'" @click="editing = !editing">
        <ChevronUp v-if="editing" class="h-4 w-4" />
        <ChevronDown v-else class="h-4 w-4" />
      </button>
    </div>

    <form v-if="editing" class="mt-4 grid gap-3 border-t border-slate-100 pt-4 dark:border-slate-800 sm:grid-cols-2" @submit.prevent="save">
      <label class="sm:col-span-2"><span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Поручение</span><input v-model="text" required maxlength="2000" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label>
      <label class="sm:col-span-2"><span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Описание</span><textarea v-model="description" rows="2" maxlength="12000" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label>
      <label><span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Срок</span><input v-model="dueAt" type="datetime-local" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label>
      <label><span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Напомнить</span><input v-model="reminderAt" type="datetime-local" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label>
      <label><span class="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">Исполнитель</span><select v-model="assignee" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950"><option value="">Без исполнителя</option><option v-for="person in staff" :key="person.id" :value="String(person.id)">{{ person.display_name }}</option></select></label>
      <div class="grid grid-cols-2 gap-2"><label><span class="mb-1 block text-xs text-slate-500">Входящее №</span><input v-model="leadId" inputmode="numeric" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label><label><span class="mb-1 block text-xs text-slate-500">Клиент №</span><input v-model="customerId" inputmode="numeric" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label></div>
      <div class="grid grid-cols-2 gap-2 sm:col-span-2"><label><span class="mb-1 block text-xs text-slate-500">Заказ №</span><input v-model="orderId" inputmode="numeric" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label><label><span class="mb-1 block text-xs text-slate-500">Оборудование №</span><input v-model="equipmentId" inputmode="numeric" class="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-600 dark:bg-slate-950" /></label></div>
      <div class="flex flex-wrap gap-2 sm:col-span-2">
        <button type="submit" :disabled="busy" class="inline-flex items-center gap-2 rounded-lg bg-[var(--kitlane-accent)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"><Save class="h-4 w-4" />Сохранить</button>
        <button v-if="task.status === 'active'" type="button" :disabled="busy" class="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 disabled:opacity-50 dark:border-red-800 dark:text-red-300" @click="emit('cancel', task)"><X class="h-4 w-4" />Отменить</button>
      </div>
    </form>
  </article>
</template>
