<script setup lang="ts">
import { ref } from 'vue';
import { leadInboxApi, notifyInboxChanged, type InboxRefusalReason } from '../../services/lead-inbox';
const props = defineProps<{ orderId: number; entityKind?: 'order' | 'lead'; mode?: 'refusal' | 'not_request' }>();
const emit = defineEmits<{ (e: 'cancel'): void; (e: 'archived'): void }>();
const reasons: { value: InboxRefusalReason; label: string }[] = [
  { value: 'profile', label: 'Не наш профиль' }, { value: 'region', label: 'Не наш регион' },
  { value: 'terms', label: 'Не подходят условия' }, { value: 'capacity', label: 'Нет ресурсов / сроков' },
  { value: 'unclear', label: 'Не хватает данных' }, { value: 'other', label: 'Другое' },
];
const mode = ref<'refusal' | 'not_request'>(props.mode || 'refusal');
const outcome = ref<'spam' | 'duplicate' | null>(null);
const reason = ref<InboxRefusalReason | null>(null);
const note = ref('');
const saving = ref(false);
const error = ref('');
const submit = async () => {
  if (saving.value) return;
  if (mode.value === 'refusal' && (!reason.value || (reason.value === 'other' && !note.value.trim()))) return;
  if (mode.value === 'not_request' && !outcome.value) return;
  saving.value = true; error.value = '';
  try {
    if (mode.value === 'refusal' && reason.value) await leadInboxApi.archive(props.orderId, reason.value, note.value.trim() || undefined, props.entityKind);
    else if (outcome.value) await leadInboxApi.archiveNonRequest(props.orderId, outcome.value, note.value.trim() || undefined, props.entityKind);
    notifyInboxChanged(); emit('archived');
  }
  catch (caught) { error.value = caught instanceof Error ? caught.message : 'Не удалось переместить обращение в архив'; }
  finally { saving.value = false; }
};
</script>
<template>
  <form class="refusal-panel" @submit.prevent="submit">
    <div class="archive-modes" aria-label="Тип решения"><button type="button" :aria-pressed="mode === 'refusal'" :disabled="saving" @click="mode = 'refusal'">Отказ</button><button type="button" :aria-pressed="mode === 'not_request'" :disabled="saving" @click="mode = 'not_request'">Не заявка</button></div>
    <h3>{{ mode === 'refusal' ? 'Почему не берём обращение?' : 'Почему это не новая заявка?' }}</h3>
    <p>Сохраним причину в архиве. Обращение можно вернуть в работу.</p>
    <div v-if="mode === 'refusal'" class="reason-options" aria-label="Причина отказа">
      <button v-for="option in reasons" :key="option.value" type="button" :aria-pressed="reason === option.value" :disabled="saving" @click="reason = option.value">{{ option.label }}</button>
    </div>
    <div v-else class="reason-options" aria-label="Классификация обращения"><button type="button" :aria-pressed="outcome === 'spam'" :disabled="saving" @click="outcome = 'spam'">Спам / ошибочное распознавание</button><button type="button" :aria-pressed="outcome === 'duplicate'" :disabled="saving" @click="outcome = 'duplicate'">Дубликат</button></div>
    <label :for="`refusal-note-${entityKind || 'order'}-${orderId}`">Комментарий {{ mode === 'refusal' && reason === 'other' ? '(обязательно)' : '(необязательно)' }}</label>
    <textarea :id="`refusal-note-${entityKind || 'order'}-${orderId}`" v-model="note" rows="2" maxlength="2000" :required="mode === 'refusal' && reason === 'other'" :disabled="saving" />
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <div class="panel-actions"><button class="inbox-button danger" type="submit" :disabled="saving || (mode === 'refusal' ? !reason || (reason === 'other' && !note.trim()) : !outcome)">{{ saving ? 'Сохраняем…' : mode === 'refusal' ? 'Не брать · в архив' : outcome === 'duplicate' ? 'Дубль · в архив' : 'Не заявка · в архив' }}</button><button class="inbox-button" type="button" :disabled="saving" @click="emit('cancel')">Отмена</button></div>
  </form>
</template>
<style scoped>
.archive-modes { display: flex; width: fit-content; gap: 3px; border-radius: 7px; background: var(--inbox-border); padding: 3px; margin-bottom: 14px; }
.archive-modes button { border-radius: 5px; padding: 7px 11px; font-size: 11px; min-height: 34px; }
.archive-modes button[aria-pressed=true] { background: var(--inbox-card); font-weight: 650; }
.refusal-panel {
  padding: 18px 21px;
  border-top: 1px solid var(--inbox-border);
  background: var(--inbox-detail);
}
h3 {
  font-size: 14px;
  font-weight: 650;
  margin: 0 0 6px;
}
p,label {
  font-size: 12px;
  color: var(--inbox-muted);
}
.reason-options,.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 12px 0;
}
.reason-options button {
  padding: 9px 12px;
  font-size: 12px;
  border: 1px solid var(--inbox-border);
  border-radius: 6px;
  background: var(--inbox-card);
}
.reason-options button[aria-pressed=true] {
  color: var(--inbox-blue);
  border-color: var(--inbox-blue);
  background: var(--inbox-selected);
}
label {
  display: block;
  margin: 12px 0 6px;
}
textarea {
  width: 100%;
  border: 1px solid var(--inbox-border);
  border-radius: 6px;
  padding: 10px;
  background: var(--inbox-card);
  font-size: 12px;
}
.error {
  color: #b94141;
}
button:disabled {
  opacity: .5;
}
</style>
