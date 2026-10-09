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
  <form class="rounded-xl border p-4 space-y-3" data-testid="call-proposal" @submit.prevent="adopt">
    <strong>{{ proposal.kind === 'incoming' ? 'Возможное обращение' : proposal.kind === 'callback' ? 'Обещанный обратный звонок' : 'Поручение' }}</strong>
    <blockquote class="text-sm text-gray-500 whitespace-pre-wrap">«{{ proposal.evidence }}»</blockquote>
    <p v-if="proposal.needs_clarification.length" class="text-sm text-amber-700">{{ proposal.needs_clarification.join(' · ') }}</p>
    <fieldset :disabled="Boolean(proposal.accepted_url) || disabled" class="space-y-3">
    <template v-if="proposal.kind === 'incoming'">
      <label class="block">Обращение<textarea v-model="incoming.request_text" class="w-full border rounded p-2" required maxlength="12000" /></label>
      <div class="grid gap-3 sm:grid-cols-2">
        <label>Телефон<input v-model="incoming.phone" class="w-full border rounded p-2" placeholder="Неизвестен" /></label>
        <label>Район<input v-model="incoming.region_text" class="w-full border rounded p-2" /></label>
        <label>Адрес<input v-model="incoming.address_text" class="w-full border rounded p-2" /></label>
        <label>Услуга<select v-model="incoming.service_type" class="w-full border rounded p-2"><option :value="null">Уточнить</option><option value="maintenance">Обслуживание</option><option value="repair">Ремонт</option><option value="turnkey">Монтаж с оборудованием</option><option value="install_only">Монтаж</option><option value="pre_install">Предмонтаж</option><option value="dismantling">Демонтаж</option></select></label>
        <label>Пожелание по времени<input v-model="incoming.requested_time_text" class="w-full border rounded p-2" /></label>
        <label>Предложенная дата (Минск)<input v-model="requestedTime" type="datetime-local" class="w-full border rounded p-2" /></label>
      </div>
      <label class="block"><input v-model="incoming.clarification_requested" type="checkbox" /> Также сохранить поручение «Уточнить адрес / созвониться перед выездом»</label>
      <p class="text-sm text-gray-500">Пожелание по времени остаётся пожеланием. Сохранение не подтверждает выезд и не создаёт заказ.</p>
    </template>
    <template v-else>
      <label class="block">Поручение<textarea v-model="task.text" class="w-full border rounded p-2" required maxlength="2000" /></label>
      <label class="block">Срок (Минск, можно оставить пустым)<input v-model="taskTime" type="datetime-local" class="border rounded p-2" /></label>
    </template>
    </fieldset>
    <a v-if="proposal.accepted_url" :href="proposal.accepted_url" class="text-blue-600">Уже сохранено — открыть</a>
    <button v-else type="submit" :disabled="disabled" class="rounded bg-blue-600 text-white px-4 py-2 disabled:opacity-50" data-testid="adopt-call-proposal">{{ proposal.kind === 'incoming' ? 'Сохранить это входящее' : 'Сохранить это поручение' }}</button>
  </form>
</template>
