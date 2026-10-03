<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { FileUp, X } from 'lucide-vue-next';
import { ManagerService, type CustomerRequisitesExtractedData, type CustomerRequisitesRecognitionResponse, type ManagerCatalogCustomerItemResponse } from '../../client';
import CreateCustomerModal from './CreateCustomerModal.vue';
import { confirmDialog } from '../../services/ui-feedback';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ customer?: ManagerCatalogCustomerItemResponse }>();
const emit = defineEmits<{ close: []; created: [customer: ManagerCatalogCustomerItemResponse]; openExisting: [id: number] }>();
const mode = ref<'text' | 'file' | 'manual'>('text');
const raw = ref('');
const file = ref<File | null>(null);
const busy = ref(false);
const saving = ref(false);
const error = ref('');
const recognition = ref<CustomerRequisitesRecognitionResponse | null>(null);
const draft = ref<CustomerRequisitesExtractedData>({});
const target = ref<ManagerCatalogCustomerItemResponse | null>(props.customer || null);
const selected = ref<Field[]>([]);
const dialog = ref<HTMLElement | null>(null);
const previousFocus = document.activeElement as HTMLElement | null;
const fields = [
  ['name', 'Название / ФИО'], ['full_legal_name', 'Полное название'], ['customer_type', 'Тип клиента'], ['inn', 'УНП'],
  ['phone', 'Телефон'], ['email', 'Email'], ['legal_address', 'Юридический адрес'], ['bank_name', 'Банк'], ['bic', 'BIC'], ['iban', 'IBAN'],
  ['signer_name', 'Подписант'], ['signer_position', 'Должность подписанта'], ['acting_basis', 'Основание полномочий'],
] as const;
type Field = typeof fields[number][0];
const warnings = computed(() => Object.values(recognition.value?.validation_flags?.warnings || {}) as string[]);
const duplicate = computed(() => recognition.value?.duplicate_customer);
const sourceMismatch = computed(() => Boolean(props.customer && duplicate.value && props.customer.id !== duplicate.value.id && duplicate.value.matched_fields?.includes('inn')));
function currentValue(key: Field) { return target.value ? (key === 'customer_type' ? target.value.type : target.value[key]) ?? null : null; }
function chooseDefaults() {
  selected.value = fields.filter(([key]) => Boolean(draft.value[key]) && (!target.value || String(draft.value[key]) !== String(currentValue(key) || ''))).map(([key]) => key);
  if (target.value) selected.value = selected.value.filter(key => !['customer_type', 'signer_position', 'acting_basis'].includes(key));
}
async function recognize() {
  if (busy.value) return;
  if (mode.value === 'text' && !raw.value.trim()) { error.value = 'Вставьте текст реквизитов'; return; }
  if (mode.value === 'file' && !file.value) { error.value = 'Выберите файл'; return; }
  busy.value = true; error.value = '';
  try {
    recognition.value = mode.value === 'text' ? await ManagerService.recognizeManagerCustomerRequisitesText({ text: raw.value }) : await ManagerService.recognizeManagerCustomerRequisites({ file: file.value! });
    draft.value = { ...recognition.value.extracted };
    if (props.customer) target.value = await ManagerService.getManagerCustomerDetail(props.customer.id);
    else target.value = null;
    chooseDefaults();
  } catch (e) { error.value = getApiErrorMessage(e); }
  finally { busy.value = false; }
}
async function chooseExisting() {
  if (!duplicate.value || busy.value) return;
  busy.value = true; error.value = '';
  try { target.value = await ManagerService.getManagerCustomerDetail(duplicate.value.id); chooseDefaults(); }
  catch (e) { error.value = getApiErrorMessage(e); }
  finally { busy.value = false; }
}
async function save() {
  if (!recognition.value || saving.value || sourceMismatch.value) return;
  if (!target.value && !draft.value.name?.trim()) { error.value = 'Укажите название или ФИО'; return; }
  saving.value = true; error.value = '';
  try {
    const applied = target.value ? selected.value : fields.map(([key]) => key).filter(key => Boolean(draft.value[key]));
    const baseline = target.value ? Object.fromEntries(applied.map(key => [key, currentValue(key as Field)])) : undefined;
    const result = await ManagerService.confirmManagerCustomerRequisites(recognition.value.id, { action: target.value ? 'update' : 'create', customer_id: target.value?.id, extracted: Object.fromEntries(applied.map(key => [key, draft.value[key]])), selected_fields: applied, baseline });
    emit('created', result.customer);
  } catch (e) { error.value = getApiErrorMessage(e); }
  finally { saving.value = false; }
}
function acceptFile(next?: File) {
  if (!next || busy.value || saving.value) return;
  if (next.size > 10 * 1024 * 1024) { error.value = 'Файл слишком большой: максимум 10 МБ'; return; }
  file.value = next; mode.value = 'file'; error.value = '';
}
function pasted(event: ClipboardEvent) { const entry = [...(event.clipboardData?.items || [])].find(item => item.kind === 'file'); if (entry) { event.preventDefault(); acceptFile(entry.getAsFile() || undefined); } }
async function close() {
  if (busy.value || saving.value) return;
  if ((recognition.value || raw.value || file.value) && !await confirmDialog({ title: 'Закрыть реквизиты?', description: 'Несохранённый результат будет потерян.', confirmText: 'Закрыть' })) return;
  emit('close');
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.stopPropagation(); void close(); }
  if (event.key !== 'Tab' || !dialog.value) return;
  const elements = [...dialog.value.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]')];
  const first = elements[0], last = elements[elements.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
}
onMounted(() => { dialog.value?.focus(); });
onUnmounted(() => { previousFocus?.focus(); });
</script>
<template>
  <CreateCustomerModal v-if="mode === 'manual'" @close="mode = 'text'" @created="emit('created', $event)" @open-existing="emit('openExisting', $event)" />
  <Teleport v-else to="body">
    <div class="intake-overlay" @click.self="close">
      <section ref="dialog" class="intake-dialog" role="dialog" aria-modal="true" aria-labelledby="intake-title" tabindex="-1" @keydown="keydown" @paste="pasted">
        <header class="intake-header"><h2 id="intake-title">{{ customer ? 'Обновить реквизиты' : 'Новый клиент' }}</h2><button type="button" aria-label="Закрыть" :disabled="busy || saving" @click="close"><X :size="19" /></button></header>
        <div class="intake-body">
          <p v-if="error" class="request-error" role="alert">{{ error }}</p>
          <template v-if="!recognition">
            <div class="intake-modes"><button type="button" :class="{active: mode === 'text'}" :disabled="busy" @click="mode = 'text'">Текст</button><button type="button" :class="{active: mode === 'file'}" :disabled="busy" @click="mode = 'file'">PDF / изображение</button><button v-if="!customer" type="button" :disabled="busy" @click="mode = 'manual'">Вручную</button></div>
            <label v-if="mode === 'text'" class="field-label">Реквизиты из письма или сообщения<textarea v-model="raw" class="field-input min-h-48" :disabled="busy" placeholder="Вставьте название, УНП, адрес, банковские реквизиты…" maxlength="12000" /></label>
            <div v-else class="file-drop" @dragover.prevent @drop.prevent="acceptFile($event.dataTransfer?.files[0])"><FileUp :size="25" /><p>Перетащите файл или вставьте скриншот</p><label class="workspace-link">Выбрать файл<input type="file" class="block mt-3 max-w-full text-xs" :disabled="busy" accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx" @change="acceptFile(($event.target as HTMLInputElement).files?.[0])" /></label><p v-if="file" class="text-sm break-all">{{ file.name }}</p><span class="muted text-xs">PDF, изображения, DOC, DOCX · до 10 МБ</span></div>
            <p class="muted text-xs mt-3">Распознавание использует Google Vision для сканов и DeepSeek для извлечения полей. Проверьте результат перед сохранением.</p>
            <div class="form-actions"><button type="button" class="btn-mini" :disabled="busy" @click="recognize">{{ busy ? 'Распознаём…' : 'Распознать' }}</button></div>
          </template>
          <template v-else>
            <div v-if="duplicate" class="duplicate-notice"><strong>{{ sourceMismatch ? 'Реквизиты относятся к другому клиенту' : 'Найден похожий клиент' }}</strong><p>{{ duplicate.name }}<span v-if="duplicate.inn"> · УНП {{ duplicate.inn }}</span></p><div class="flex flex-wrap gap-3 mt-2"><button v-if="!customer && !target" type="button" class="workspace-link" :disabled="busy" @click="chooseExisting">Обновить этого клиента</button><button type="button" class="workspace-link" @click="emit('openExisting', duplicate.id)">Открыть карточку</button></div></div>
            <p v-if="target" class="text-sm mb-3">Обновление: <strong>{{ target.name }}</strong>. Выберите поля для замены.</p>
            <p v-for="warning in warnings" :key="warning" class="text-xs text-amber-700 dark:text-amber-300 my-2">{{ warning }}</p>
            <form @submit.prevent="save">
              <div class="recognition-fields" :class="{updating: target}">
                <template v-for="[key,label] in fields" :key="key">
                  <label class="recognition-label"><input v-if="target" v-model="selected" type="checkbox" :value="key" :disabled="saving" /><span>{{ label }}</span></label>
                  <div v-if="target" class="old-value">{{ currentValue(key) || '—' }}</div>
                  <div><select v-if="key === 'customer_type'" v-model="draft.customer_type" class="field-input" aria-label="Тип клиента" :disabled="saving"><option value="individual">Физлицо</option><option value="individual_entrepreneur">ИП</option><option value="company">Юрлицо</option></select><input v-else v-model="draft[key]" class="field-input" :aria-label="label" :disabled="saving" :type="key === 'email' ? 'email' : 'text'" :required="key === 'name' && !target" /><span v-if="recognition.validation_flags?.field_errors?.[key]" class="field-error">{{ recognition.validation_flags.field_errors[key] }} — исправьте значение</span></div>
                </template>
              </div>
              <details class="mt-4 text-xs"><summary class="workspace-link cursor-pointer">Исходный текст</summary><pre class="source-text">{{ recognition.raw_text }}</pre></details>
              <div class="form-actions"><button type="button" class="btn-mini-outline" :disabled="saving" @click="recognition = null">Назад</button><button type="submit" class="btn-mini" :disabled="saving || busy || sourceMismatch || Boolean(target && !selected.length)">{{ saving ? 'Сохраняем…' : target ? 'Применить изменения' : 'Создать клиента' }}</button></div>
            </form>
          </template>
        </div>
      </section>
    </div>
  </Teleport>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.intake-overlay { position: fixed; inset: 0; z-index: 90; display: flex; align-items: center; justify-content: center; background: #0008; padding: 16px; }.intake-dialog { width: min(860px,100%); max-height: 92dvh; background: var(--mv-surface); color: var(--mv-text); border-radius: 12px; border: 1px solid var(--mv-border); display: flex; flex-direction: column; }.intake-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--mv-border); }.intake-header h2 { font-size: 17px; font-weight: 700; }.intake-body { padding: 18px; overflow: auto; }.intake-modes { display: flex; gap: 5px; margin-bottom: 16px; background: var(--mv-bg); padding: 3px; border-radius: 8px; }.intake-modes button { padding: 7px 12px; font-size: 13px; border-radius: 6px; }.intake-modes .active { background: var(--mv-surface); color: var(--kitlane-accent-text); }.file-drop { display: grid; justify-items: center; gap: 12px; border: 1px dashed var(--mv-border); border-radius: 9px; padding: 24px 12px; }.recognition-fields { display: grid; grid-template-columns: 160px minmax(0,1fr); gap: 10px; align-items: center; }.recognition-fields.updating { grid-template-columns: 145px minmax(0,1fr) minmax(0,1fr); }.recognition-label { display: flex; align-items: center; gap: 8px; font-size: 12px; }.old-value { font-size: 12px; color: var(--mv-text-muted); overflow-wrap: anywhere; }.duplicate-notice { padding: 12px; background: var(--kitlane-accent-soft); border-radius: 8px; margin-bottom: 16px; font-size: 13px; }.source-text { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--mv-bg); padding: 12px; margin-top: 10px; max-height: 240px; overflow: auto; }
@media(max-width:600px) { .intake-overlay { padding: 8px; }.intake-body { padding: 12px; }.recognition-fields,.recognition-fields.updating { grid-template-columns: 1fr; gap: 5px; }.recognition-label { margin-top: 8px; }.old-value:before { content: 'Сейчас: '; }.intake-modes button { padding: 6px 8px; font-size: 12px; } }
</style>
