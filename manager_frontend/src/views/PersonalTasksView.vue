<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Bell, Loader2, Plus } from 'lucide-vue-next';

import PersonalTaskCard from '../components/tasks/PersonalTaskCard.vue';
import {
  changePersonalTaskStatus,
  createPersonalTask,
  getPersonalTask,
  listPersonalTaskAssignees,
  listPersonalTasks,
  newPersonalTaskCommandKey,
  updatePersonalTask,
  type PersonalTask,
  type PersonalTaskAssignee,
  type PersonalTaskFilter,
  type PersonalTaskUpdate,
} from '../services/personal-tasks-api';
import { getApiErrorMessage } from '../utils/api-errors';

const filters: Array<{ value: PersonalTaskFilter; label: string }> = [
  { value: 'active', label: 'Активные' },
  { value: 'today', label: 'Сегодня' },
  { value: 'overdue', label: 'Просроченные' },
  { value: 'undated', label: 'Без срока' },
  { value: 'completed', label: 'Завершённые' },
  { value: 'cancelled', label: 'Отменённые' },
];

const selectedFilter = ref<PersonalTaskFilter>('active');
const tasks = ref<PersonalTask[]>([]);
const focusedTaskId = ref(Number(new URLSearchParams(window.location.search).get('taskId')) || null);
const focusedTask = ref<PersonalTask | null>(null);
const staff = ref<PersonalTaskAssignee[]>([]);
const loading = ref(true);
const creating = ref(false);
const busyId = ref<number | null>(null);
const text = ref('');
const error = ref('');
const notice = ref('');
const dueReminderCount = ref(0);
type PendingCommand = { signature: string; key: string };
let pendingCreate: PendingCommand | null = null;
const pendingMutations = new Map<number, PendingCommand>();
watch(() => text.value.trim(), () => { pendingCreate = null; }, { flush: 'sync' });

const uncertainResult = (caught: unknown): boolean => {
  const status = Number((caught as { status?: number } | null)?.status);
  return !status || status === 408 || status >= 500;
};

const commandFor = (previous: PendingCommand | undefined | null, signature: string): PendingCommand => (
  previous?.signature === signature ? previous : { signature, key: newPersonalTaskCommandKey() }
);

const emptyMessage = computed(() => selectedFilter.value === 'active'
  ? 'Активных поручений нет.'
  : 'В этом списке поручений нет.');

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const result = await listPersonalTasks(selectedFilter.value);
    tasks.value = result.items;
    dueReminderCount.value = result.due_reminder_count;
    if (focusedTaskId.value) focusedTask.value = await getPersonalTask(focusedTaskId.value);
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    loading.value = false;
  }
};

const loadStaff = async () => {
  try {
    staff.value = (await listPersonalTaskAssignees()).items;
  } catch {
    staff.value = [];
  }
};

const chooseFilter = async (filter: PersonalTaskFilter) => {
  if (selectedFilter.value === filter && !focusedTaskId.value) return;
  selectedFilter.value = filter;
  focusedTaskId.value = null;
  focusedTask.value = null;
  await load();
};

const create = async () => {
  const value = text.value.trim();
  if (!value || creating.value) return;
  creating.value = true;
  error.value = '';
  const command = commandFor(pendingCreate, value);
  pendingCreate = command;
  try {
    await createPersonalTask({ text: value }, command.key);
    if (pendingCreate === command) pendingCreate = null;
    if (text.value.trim() === value) text.value = '';
    notice.value = 'Поручение сохранено';
    selectedFilter.value = 'active';
    await load();
  } catch (caught) {
    if (!uncertainResult(caught) && pendingCreate === command) pendingCreate = null;
    error.value = getApiErrorMessage(caught);
  } finally {
    creating.value = false;
  }
};

const mutate = async (task: PersonalTask, signature: string, action: (key: string) => Promise<PersonalTask>, message: string) => {
  if (busyId.value !== null) return;
  const command = commandFor(pendingMutations.get(task.id), signature);
  pendingMutations.set(task.id, command);
  busyId.value = task.id;
  error.value = '';
  try {
    await action(command.key);
    pendingMutations.delete(task.id);
    notice.value = message;
    await load();
  } catch (caught) {
    const errorMessage = getApiErrorMessage(caught);
    if (!uncertainResult(caught)) {
      pendingMutations.delete(task.id);
      await load();
    }
    error.value = errorMessage;
  } finally {
    busyId.value = null;
  }
};

const toggle = (task: PersonalTask) => {
  const action = task.status === 'active' ? 'complete' : 'reopen';
  return mutate(task, JSON.stringify([action, task.version]),
    key => changePersonalTaskStatus(task.id, action, task.version, key),
    action === 'complete' ? 'Поручение завершено' : 'Поручение возвращено');
};

const cancel = (task: PersonalTask) => mutate(
  task,
  JSON.stringify(['cancel', task.version]),
  key => changePersonalTaskStatus(task.id, 'cancel', task.version, key),
  'Поручение отменено',
);

const save = (task: PersonalTask, payload: PersonalTaskUpdate) => mutate(
  task,
  JSON.stringify(['edit', payload]),
  key => updatePersonalTask(task.id, { ...payload }, key),
  'Поручение обновлено',
);

onMounted(() => {
  void load();
  void loadStaff();
});
</script>

<template>
  <main class="mx-auto w-full max-w-5xl p-4 sm:p-6">
    <header class="mb-5">
      <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Поручения</h1>
      <p class="mt-1 text-sm text-slate-600 dark:text-slate-300">Быстрые дела без обязательного заказа и срока.</p>
    </header>

    <form class="mb-4 flex gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900" @submit.prevent="create">
      <input v-model="text" data-testid="personal-task-create-text" maxlength="2000" required placeholder="Например: дослать коммерческое предложение" aria-label="Новое поручение" class="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2.5 dark:border-slate-600 dark:bg-slate-950" />
      <button type="submit" data-testid="personal-task-create" :disabled="creating || !text.trim()" class="inline-flex shrink-0 items-center gap-2 rounded-lg bg-[var(--kitlane-accent)] px-4 py-2.5 font-semibold text-white disabled:opacity-50"><Loader2 v-if="creating" class="h-4 w-4 animate-spin" /><Plus v-else class="h-4 w-4" /><span class="hidden sm:inline">Добавить</span></button>
    </form>

    <div v-if="dueReminderCount" class="mb-4 flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-900 dark:border-amber-500/50 dark:bg-amber-950/30 dark:text-amber-200"><Bell class="h-4 w-4 shrink-0" />Напоминаний к этому моменту: {{ dueReminderCount }}</div>
    <p v-if="error" class="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300" role="alert">{{ error }}</p>
    <p v-if="notice" class="sr-only" role="status">{{ notice }}</p>

    <div class="mb-4 flex gap-2 overflow-x-auto pb-1" aria-label="Фильтры поручений">
      <button v-for="filter in filters" :key="filter.value" type="button" class="whitespace-nowrap rounded-full px-3 py-2 text-sm font-medium" :class="selectedFilter === filter.value ? 'bg-[var(--kitlane-accent)] text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'" @click="chooseFilter(filter.value)">{{ filter.label }}</button>
    </div>

    <div v-if="loading" class="flex justify-center py-12 text-slate-500"><Loader2 class="h-6 w-6 animate-spin" /></div>
    <section v-else-if="focusedTask" data-testid="linked-personal-task"><h2 class="mb-2 font-semibold">Связанное поручение #{{ focusedTask.id }}</h2><PersonalTaskCard :task="focusedTask" :staff="staff" :busy="busyId === focusedTask.id" @toggle="toggle" @cancel="cancel" @save="save" /></section>
    <p v-else-if="!tasks.length" class="rounded-xl border border-dashed border-slate-300 px-4 py-10 text-center text-slate-500 dark:border-slate-700">{{ emptyMessage }}</p>
    <div v-else class="grid gap-3">
      <PersonalTaskCard v-for="task in tasks" :key="task.id" :task="task" :staff="staff" :busy="busyId === task.id" @toggle="toggle" @cancel="cancel" @save="save" />
    </div>
  </main>
</template>
