<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { Inbox, ListTodo, Plus, X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { createPersonalTask, newPersonalTaskCommandKey, notifyPersonalTasksChanged } from '../../services/personal-tasks-api';
import { notifyInboxChanged, globalIncomingCapturedEvent } from '../../services/lead-inbox';
import { readOrderPage } from '../../services/order-navigation';
import { getApiErrorMessage } from '../../utils/api-errors';
import QuickIncomingCapture from '../leads/QuickIncomingCapture.vue';

const props = defineProps<{ location: string; canCreateTask: boolean; compact: boolean }>();
const emit = defineEmits<{ notice: [message: string] }>();
const step = ref<'choose' | 'task' | 'incoming' | null>(null);
const dialog = ref<HTMLElement | null>(null);
const input = ref<HTMLTextAreaElement | null>(null);
const text = ref('');
const due = ref('');
const reminder = ref('');
const details = ref(false);
const saving = ref(false);
const error = ref('');
const commandKey = ref('');
const signature = ref('');
const contextLocation = ref(props.location);
const taskShortcut = computed(() => props.canCreateTask && Boolean(readOrderPage(props.location)));
const binding = computed(() => {
  const url = new URL(contextLocation.value, window.location.origin);
  const positiveId = (key: string) => { const value = Number(url.searchParams.get(key)); return Number.isSafeInteger(value) && value > 0 ? value : undefined; };
  const order = readOrderPage(contextLocation.value);
  if (order) return { label: 'Заказ №' + order.orderId, fields: { order_id: order.orderId } };
  const customer = positiveId('customerId');
  if (url.pathname === '/manager/customers/profile' && customer) return { label: 'Клиент №' + customer, fields: { customer_id: customer } };
  const lead = positiveId('incomingId') || (url.searchParams.get('kind') === 'lead' ? positiveId('itemId') : undefined);
  if (url.pathname === '/manager/leads' && lead) return { label: 'Входящее №' + lead, fields: { lead_id: lead } };
  const inboxOrder = url.searchParams.get('kind') === 'order' ? positiveId('itemId') : undefined;
  if (url.pathname === '/manager/leads' && inboxOrder) return { label: 'Входящее №' + inboxOrder, fields: { order_id: inboxOrder } };
  return { label: '', fields: {} };
});
const clear = () => { text.value = ''; due.value = ''; reminder.value = ''; details.value = false; error.value = ''; signature.value = ''; };
const close = () => { if (!saving.value) step.value = null; };
useDialogA11y({ open: computed(() => step.value !== null), dialogRef: dialog, initialFocusRef: input, close });
watch(() => props.location, () => { step.value = null; clear(); });
const chooseTask = async () => { step.value = 'task'; await nextTick(); input.value?.focus(); };
const chooseIncoming = async () => {
  step.value = 'incoming';
  await nextTick();
  dialog.value?.querySelector<HTMLElement>('textarea, input')?.focus();
};
const open = () => {
  const location = window.location.pathname + window.location.search;
  if (contextLocation.value !== location) clear();
  contextLocation.value = location;
  if (taskShortcut.value) void chooseTask();
  else if (props.canCreateTask) step.value = 'choose';
  else void chooseIncoming();
};
const create = async () => {
  if (saving.value || !props.canCreateTask || !text.value.trim()) return;
  const payload = {
    text: text.value.trim(), ...binding.value.fields,
    ...(due.value ? { due_at: new Date(due.value).toISOString() } : {}),
    ...(reminder.value ? { reminder_at: new Date(reminder.value).toISOString() } : {}),
  };
  const next = JSON.stringify(payload);
  if (next !== signature.value) { signature.value = next; commandKey.value = newPersonalTaskCommandKey(); }
  saving.value = true; error.value = '';
  try {
    await createPersonalTask(payload, commandKey.value);
    notifyPersonalTasksChanged();
    clear(); step.value = null;
    emit('notice', 'Поручение сохранено');
  } catch (caught) { error.value = getApiErrorMessage(caught); }
  finally { saving.value = false; }
};
const captured = (record: { lead_id: number }) => {
  notifyInboxChanged(); window.dispatchEvent(new Event(globalIncomingCapturedEvent));
  emit('notice', 'Входящее №' + record.lead_id + ' сохранено');
};
</script>

<template>
  <button type="button" class="quick-trigger" :aria-label="taskShortcut ? 'Записать поручение' : 'Создать'" :title="taskShortcut ? 'Записать поручение' : 'Создать'" aria-haspopup="dialog" :aria-expanded="Boolean(step)" @click="open">
    <component :is="taskShortcut ? ListTodo : Plus" :size="18" aria-hidden="true" /><span :class="{ 'sr-only': compact }">{{ taskShortcut ? 'Поручение' : 'Создать' }}</span>
  </button>
  <Teleport to="body">
    <div v-if="step" class="quick-backdrop" @click.self="close">
      <section ref="dialog" class="quick-dialog" role="dialog" aria-modal="true" :aria-label="step === 'task' ? 'Новое поручение' : step === 'incoming' ? 'Новое обращение' : 'Создать'" tabindex="-1">
        <QuickIncomingCapture v-if="step === 'incoming'" @close="close" @captured="captured" @saved="captured" />
        <template v-else>
          <header><h2>{{ step === 'choose' ? 'Создать' : 'Новое поручение' }}</h2><button type="button" class="quick-icon" aria-label="Закрыть" :disabled="saving" @click="close"><X :size="19" /></button></header>
          <div v-if="step === 'choose'" class="choices">
            <button type="button" @click="chooseIncoming"><Inbox :size="18" />Обращение</button>
            <button v-if="canCreateTask" type="button" @click="chooseTask"><ListTodo :size="18" />Поручение</button>
          </div>
          <form v-else class="quick-form" @submit.prevent="create">
            <p v-if="binding.label" class="quick-context">Связано с карточкой · {{ binding.label }}</p>
            <label>Что нужно сделать<textarea ref="input" v-model="text" maxlength="2000" required rows="3" placeholder="Например, выслать письмо с предложением" :disabled="saving" /></label>
            <button type="button" class="optional-fields" :aria-expanded="details" @click="details = !details">Срок и напоминание</button>
            <div v-if="details" class="quick-dates"><label>Срок<input v-model="due" type="datetime-local" :disabled="saving" /></label><label>Напомнить<input v-model="reminder" type="datetime-local" :disabled="saving" /></label></div>
            <p v-if="error" role="alert" class="text-red-700 dark:text-red-300">{{ error }}</p>
            <div class="quick-actions">
              <button v-if="taskShortcut" type="button" class="optional-fields" :disabled="saving" @click="chooseIncoming">Новое обращение</button>
              <button type="submit" class="quick-save" :disabled="saving || !text.trim()">{{ saving ? 'Сохраняем…' : 'Сохранить поручение' }}</button>
            </div>
          </form>
        </template>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.quick-trigger,.quick-icon,.choices button { display:inline-flex; align-items:center; justify-content:center; gap:.35rem; min-height:40px; }
.quick-trigger { background:var(--kitlane-accent); color:white; padding:0 .7rem; border-radius:.55rem; font-size:.875rem; font-weight:650; }
.quick-backdrop { position:fixed; inset:0; z-index:90; background:rgb(9 21 38 / .48); display:grid; align-items:center; justify-items:center; padding:1rem; }
.quick-dialog { background:var(--kitlane-surface); color:var(--kitlane-text); border-radius:1rem; width:min(100%,31rem); max-height:90dvh; overflow:auto; overscroll-behavior:contain; }
.quick-dialog header { display:flex; align-items:center; justify-content:space-between; padding:.55rem 1rem; }
.quick-dialog h2 { font-size:1.15rem; font-weight:700; }
.quick-icon { width:40px; }
.choices,.quick-form { display:grid; gap:.75rem; padding:.25rem 1rem 1rem; }
.choices button { justify-content:start; min-height:48px; padding:0 .65rem; border:1px solid var(--kitlane-border); border-radius:.55rem; }
.choices button:hover,.optional-fields:hover { background:var(--kitlane-accent-soft); }
.quick-form label { display:grid; gap:.35rem; font-size:.875rem; font-weight:600; min-width:0; }
.quick-form textarea,.quick-form input { padding:.55rem; border:1px solid var(--kitlane-border); border-radius:.5rem; background:var(--kitlane-surface); width:100%; min-width:0; }
.quick-context { color:var(--kitlane-muted); font-size:.875rem; }
.optional-fields { justify-self:start; min-height:40px; color:var(--kitlane-accent-text); font-size:.875rem; }
.quick-dates { display:grid; gap:.65rem; }
.quick-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; align-items:center; gap:.75rem; }
.quick-actions .optional-fields { margin-right:auto; }
.quick-save { padding:.65rem 1rem; background:var(--kitlane-accent); color:white; border-radius:.55rem; justify-self:end; font-weight:650; }
.quick-save:disabled { opacity:.55; }
@media(max-width:767px){.quick-trigger{min-height:44px;min-width:44px;padding:0 .5rem;} .quick-trigger span{display:none;} .quick-backdrop{align-items:end;padding:0;} .quick-dialog{width:100%;max-height:90dvh;border-radius:1rem 1rem 0 0;padding-bottom:env(safe-area-inset-bottom);}.quick-form input,.quick-form textarea{font-size:16px;} }
</style>
