<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { leadInboxApi, type InboxItem, type InboxHistory } from '../../services/lead-inbox';
const props = defineProps<{ item: InboxItem }>();
const emit = defineEmits<{ (e: 'updated', item: InboxItem, history: InboxHistory[]): void }>();
const saving = ref(false);
const error = ref('');
const deadline = ref('');
const sourceUrl = ref('');
const isTender = computed(() => props.item.source_kind === 'tender');
const minskLocal = (value?: string | null) => {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return new Date(parsed.getTime() + 3 * 60 * 60 * 1000).toISOString().slice(0, 16);
};
watch(() => [props.item.id, props.item.deadline_at, props.item.tender?.url, isTender.value], () => {
  deadline.value = minskLocal(props.item.deadline_at);
  sourceUrl.value = props.item.tender?.url || '';
}, { immediate: true });
const save = async (tender: boolean, confirmDeadline = false) => {
  if (saving.value) return;
  saving.value = true; error.value = '';
  try {
    const result = await leadInboxApi.tender(props.item.id, {
      is_tender: tender,
      deadline_at: tender && confirmDeadline && deadline.value ? new Date(`${deadline.value}+03:00`).toISOString() : null,
      source_url: tender && confirmDeadline ? sourceUrl.value.trim() || null : null,
    });
    emit('updated', result, result.history || []);
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Не удалось сохранить контекст тендера'; }
  finally { saving.value = false; }
};
</script>
<template>
  <div class="email-tender-context">
    <button type="button" class="classification-toggle" :aria-expanded="isTender" :aria-controls="`email-tender-fields-${item.id}`" :disabled="saving" @click="save(!isTender)">{{ isTender ? 'Это обычное обращение' : 'Это тендер' }}</button>
    <form v-if="isTender" :id="`email-tender-fields-${item.id}`" class="tender-fields" @submit.prevent="save(true, true)">
      <p>Подтвердите срок подачи из оригинала закупки.</p>
      <div class="field-row"><label :for="`email-tender-deadline-${item.id}`">Срок подачи (Минск, необязательно)<input :id="`email-tender-deadline-${item.id}`" v-model="deadline" type="datetime-local" :disabled="saving" /></label><label :for="`email-tender-url-${item.id}`">Ссылка на закупку (необязательно)<input :id="`email-tender-url-${item.id}`" v-model="sourceUrl" type="url" pattern="https?://.+" placeholder="https://…" :disabled="saving" /></label></div>
      <button type="submit" class="inbox-button" :disabled="saving">{{ saving ? 'Сохраняем…' : deadline ? 'Подтвердить срок подачи' : 'Сохранить без срока подачи' }}</button>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
  </div>
</template>
<style scoped>
.email-tender-context { margin-top: 16px; }
.classification-toggle { color: var(--inbox-blue); text-decoration: underline; text-underline-offset: 3px; min-height: 36px; }
p { font-size: 11px; color: var(--inbox-muted); margin: 5px 0 10px; }
.field-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
label { flex: 1; min-width: 200px; font-size: 11px; color: var(--inbox-muted); }
input { display: block; width: 100%; margin-top: 5px; padding: 9px; border: 1px solid var(--inbox-border); border-radius: 6px; background: var(--inbox-card); color: inherit; font-size: 12px; }
.error { color: #b94141; }
button:disabled { opacity: .5; }
</style>
