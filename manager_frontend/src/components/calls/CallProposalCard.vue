<script setup lang="ts">
import { ref } from 'vue';
import type { CallAdoptPayload, CallProposalResponse, IncomingFields, PersonalTaskCreatePayload } from '../../client';
import { minskDateTime, minskIso } from '../../services/call-recordings-api';

const props = defineProps<{ proposal: CallProposalResponse; version: number; disabled: boolean }>();
const emit = defineEmits<{ adopt: [number, CallAdoptPayload] }>();
const incoming = ref<IncomingFields>(props.proposal.payload as IncomingFields);
const task = ref<PersonalTaskCreatePayload>(props.proposal.payload as PersonalTaskCreatePayload);
const taskTime = ref(minskDateTime(task.value.due_at));
const requestedTime = ref(minskDateTime(incoming.value.requested_at));
function adopt() {
  const payload: CallAdoptPayload = { expected_version: props.version };
  if (props.proposal.kind === 'incoming') payload.incoming = { ...incoming.value, requested_at: minskIso(requestedTime.value) };
  else payload.task = { ...task.value, due_at: minskIso(taskTime.value) };
  emit('adopt', props.proposal.id, payload);
}
</script>

<template>
  <form class="proposal-card space-y-4 rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 dark:border-slate-800 dark:bg-slate-900" data-testid="call-proposal" @submit.prevent="adopt">
    <strong class="block text-base font-semibold">{{ proposal.kind === 'incoming' ? 'Возможное обращение' : proposal.kind === 'callback' ? 'Обещанный обратный звонок' : 'Поручение' }}</strong>
    <blockquote class="rounded-xl border-l-2 border-brand-300 bg-slate-50 p-3 text-sm leading-6 text-slate-600 whitespace-pre-wrap break-words dark:bg-slate-950/60 dark:text-slate-300">«{{ proposal.evidence }}»</blockquote>
    <p v-if="proposal.needs_clarification.length" class="rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">{{ proposal.needs_clarification.join(' · ') }}</p>
    <fieldset :disabled="Boolean(proposal.accepted_url) || disabled" class="space-y-4 min-w-0">
    <template v-if="proposal.kind === 'incoming'">
      <label class="block">Обращение<textarea v-model="incoming.request_text" class="proposal-input" rows="4" required maxlength="12000" /></label>
      <div class="grid gap-3 sm:grid-cols-2">
        <label>Телефон<input v-model="incoming.phone" class="proposal-input" placeholder="Неизвестен" /></label>
        <label>Район<input v-model="incoming.region_text" class="proposal-input" /></label>
        <label>Адрес<input v-model="incoming.address_text" class="proposal-input" /></label>
        <label>Услуга<select v-model="incoming.service_type" class="proposal-input"><option :value="null">Уточнить</option><option value="maintenance">Обслуживание</option><option value="repair">Ремонт</option><option value="turnkey">Монтаж с оборудованием</option><option value="install_only">Монтаж</option><option value="pre_install">Предмонтаж</option><option value="dismantling">Демонтаж</option></select></label>
        <label>Пожелание по времени<input v-model="incoming.requested_time_text" class="proposal-input" /></label>
        <label>Точное время (Минск, если уточнено)<input v-model="requestedTime" type="datetime-local" class="proposal-input" /></label>
        <p v-if="proposal.date_precision === 'date' && proposal.requested_date" data-testid="call-desired-day" class="rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 sm:col-span-2 dark:bg-slate-950/60 dark:text-slate-400">Желаемый день (Минск): {{ proposal.requested_date.split('-').reverse().join('.') }}. Точное время не указано.</p>
      </div>
      <label class="flex items-start gap-2 rounded-xl bg-slate-50 p-3 text-sm dark:bg-slate-950/60"><input v-model="incoming.clarification_requested" type="checkbox" class="mt-1 h-4 w-4 shrink-0 accent-brand-600" /> Также сохранить поручение «Уточнить адрес / созвониться перед выездом»</label>
      <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">Пожелание по времени остаётся пожеланием. Сохранение не подтверждает выезд и не создаёт заказ.</p>
    </template>
    <template v-else>
      <label class="block">Поручение<textarea v-model="task.text" class="proposal-input" rows="3" required maxlength="2000" /></label>
      <label class="block">Срок (Минск, можно оставить пустым)<input v-model="taskTime" type="datetime-local" class="proposal-input" /></label>
    </template>
    </fieldset>
    <a v-if="proposal.accepted_url" :href="proposal.accepted_url" class="inline-flex text-sm font-medium text-brand-600 hover:underline dark:text-brand-400">Уже сохранено — открыть</a>
    <button v-else type="submit" :disabled="disabled" class="w-full rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto" data-testid="adopt-call-proposal">{{ proposal.kind === 'incoming' ? 'Сохранить это входящее' : 'Сохранить это поручение' }}</button>
  </form>
</template>

<style scoped>
.proposal-card { @apply text-slate-900 dark:text-slate-100; }
.proposal-card:is(.dark *) { color-scheme: dark; }
.proposal-card label { @apply text-sm font-medium text-slate-600 dark:text-slate-300; }
.proposal-input { @apply mt-1 block w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-normal leading-6 text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100; }
</style>
