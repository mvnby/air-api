<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { Mail, Pencil, Phone, Plus } from 'lucide-vue-next';
import { ManagerService, type ManagerCatalogCustomerItemResponse } from '../../client';
import type { SavedContacts } from './customer-completeness';
import { getApiErrorMessage } from '../../utils/api-errors';
import { notify } from '../../services/ui-feedback';

const props = defineProps<{ customer: ManagerCatalogCustomerItemResponse; editInitially?: boolean }>();
const emit = defineEmits<{ updated: []; dirty: [value: boolean]; loaded: [value: SavedContacts] }>();
type Contact = { id?: number | null; name?: string | null; role?: string | null; phone?: string | null; email?: string | null; is_primary?: boolean; is_active?: boolean };
type History = { id: number; field_name: string; old_value?: string | null; new_value?: string | null; author_name?: string | null; changed_at: string };
const items = ref<Contact[]>([]);
const history = ref<History[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const historyError = ref('');
const historyLoading = ref(false);
const showInactive = ref(false);
const showHistory = ref(false);
const editing = ref<number | 'new' | 'legacy' | null>(null);
const form = ref({ name: '', role: '', phone: '', email: '', is_primary: false, is_active: true });
const original = ref('');
const dirty = computed(() => editing.value !== null && JSON.stringify(form.value) !== original.value);
watch(dirty, (value) => emit('dirty', value));
const visibleContacts = computed(() => items.value.filter((item) => showInactive.value || item.is_active));
const hasLegacyContact = computed(() => !items.value.length && Boolean(props.customer.phone || props.customer.email));
const labels: Record<string, string> = { name: 'Имя', role: 'Роль', phone: 'Телефон', email: 'Email', is_primary: 'Основной контакт', is_active: 'Актуальность' };

let alive = true;
onUnmounted(() => { alive = false; });
async function load() {
  loading.value = true;
  error.value = '';
  const customerId = props.customer.id;
  try {
    const result = await ManagerService.getManagerCustomerContacts(customerId);
    if (!alive) return;
    items.value = result.items;
    emit('loaded', { customerId, items: result.items });
  }
  catch (e) { if (alive) { error.value = getApiErrorMessage(e); emit('loaded', { customerId, items: null }); } }
  finally { loading.value = false; }
}
async function loadHistory() {
  historyLoading.value = true;
  historyError.value = '';
  try { history.value = (await ManagerService.getManagerCustomerContactHistory(props.customer.id)).items; }
  catch (e) { historyError.value = getApiErrorMessage(e); }
  finally { historyLoading.value = false; }
}
watch(showHistory, (value) => { if (value) void loadHistory(); });
function edit(item?: Contact) {
  editing.value = item ? (item.id ?? 'legacy') : 'new';
  form.value = { name: item?.name || '', role: item?.role || '', phone: item?.phone || '', email: item?.email || '', is_primary: item?.is_primary ?? !items.value.some((c) => c.is_primary && c.is_active), is_active: item?.is_active ?? true };
  original.value = JSON.stringify(form.value);
  error.value = '';
}
function editLegacy() { edit({ id: null, name: props.customer.type === 'individual' ? props.customer.name || '' : '', phone: props.customer.phone, email: props.customer.email, is_primary: true, is_active: true }); }
function cancel() { editing.value = null; error.value = ''; }
async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const payload = { ...form.value, name: form.value.name.trim(), role: form.value.role.trim() || null, phone: form.value.phone.trim() || null, email: form.value.email.trim() || null };
    if (typeof editing.value === 'number') await ManagerService.patchManagerCustomerContact(props.customer.id, editing.value, payload);
    else await ManagerService.createManagerCustomerContact(props.customer.id, payload);
    editing.value = null;
    emit('dirty', false);
    emit('updated');
    await load();
    if (showHistory.value) await loadHistory();
    notify('Контакт сохранён', 'success');
  } catch (e) { error.value = getApiErrorMessage(e); }
  finally { saving.value = false; }
}
function historyValue(value: unknown) { if (value === 'true' || value === 'True' || value === true) return 'Да'; if (value === 'false' || value === 'False' || value === false) return 'Нет'; return value || '—'; }
onMounted(async () => { await load(); if (props.editInitially && !error.value) { const primary = items.value.find((c) => c.is_primary && c.is_active); if (primary) edit(primary); else if (hasLegacyContact.value) editLegacy(); else edit(); } });
</script>

<template>
  <section class="customer-panel" aria-label="Контакты клиента">
    <div class="panel-heading"><h2>Контакты <span v-if="items.length" class="muted text-xs font-normal">{{ items.length }}</span></h2><button class="workspace-link inline-flex items-center gap-1" type="button" :disabled="editing !== null" @click="edit()"><Plus :size="15" /> Добавить</button></div>
    <p v-if="error" role="alert" class="request-error">{{ error }} <button v-if="editing === null" class="workspace-link" type="button" @click="load">Повторить</button></p>
    <p v-if="loading" class="muted text-sm">Загрузка контактов…</p>
    <template v-else>
      <div v-if="hasLegacyContact && editing !== 'legacy'" class="contact-row">
        <div class="contact-heading"><strong>{{ customer.type === 'individual' ? customer.name : 'Основной контакт' }}</strong><button class="workspace-link" type="button" :disabled="editing !== null" @click="editLegacy">Изменить</button></div>
        <div class="contact-links"><a v-if="customer.phone" :href="`tel:${customer.phone}`"><Phone :size="14" />{{ customer.phone }}</a><a v-if="customer.email" :href="`mailto:${customer.email}`"><Mail :size="14" />{{ customer.email }}</a></div>
      </div>
      <div v-for="contact in visibleContacts" :key="contact.id ?? 'legacy'" class="contact-row" :class="{ inactive: !contact.is_active }">
        <div class="contact-heading"><div><strong>{{ contact.name || 'Основной контакт' }}</strong><span v-if="contact.is_primary" class="badge ml-2">Основной</span><p v-if="contact.role" class="muted text-xs mt-1">{{ contact.role }}</p><span v-if="!contact.is_active" class="muted text-xs">Неактивен</span></div><button class="workspace-link" type="button" :disabled="editing !== null" :aria-label="`Изменить контакт ${contact.name || 'основной'}`" @click="edit(contact)"><Pencil :size="15" /></button></div>
        <div class="contact-links"><a v-if="contact.phone" :href="`tel:${contact.phone}`"><Phone :size="14" />{{ contact.phone }}</a><a v-if="contact.email" :href="`mailto:${contact.email}`"><Mail :size="14" />{{ contact.email }}</a></div>
      </div>
      <p v-if="!items.length && !hasLegacyContact && editing === null && !error" class="muted text-sm">Добавьте человека, с которым можно связаться.</p>
      <form v-if="editing !== null" class="contact-form" @submit.prevent="save">
        <h3 class="font-semibold text-sm mb-3">{{ editing === 'new' ? 'Новый контакт' : 'Изменить контакт' }}</h3>
        <div class="form-grid">
          <label class="field-label">Имя<input v-model="form.name" class="field-input" name="contact_name" required maxlength="200" :disabled="saving" autocomplete="off" /></label>
          <label class="field-label">Роль<input v-model="form.role" class="field-input" name="contact_role" placeholder="Бухгалтер, инженер…" maxlength="120" :disabled="saving" /></label>
          <label class="field-label">Телефон<input v-model="form.phone" class="field-input" name="contact_phone" type="tel" :disabled="saving" /></label>
          <label class="field-label">Email<input v-model="form.email" class="field-input" name="contact_email" type="email" :disabled="saving" /></label>
        </div>
        <div class="flex flex-wrap gap-4 mt-3 text-sm"><label class="inline-flex gap-2 items-center"><input v-model="form.is_primary" type="checkbox" :disabled="saving || !form.is_active" />Основной контакт</label><label class="inline-flex gap-2 items-center"><input v-model="form.is_active" type="checkbox" :disabled="saving" @change="!form.is_active && (form.is_primary = false)" />Актуален</label></div>
        <div class="form-actions"><button class="btn-mini-outline" type="button" :disabled="saving" @click="cancel">Отмена</button><button class="btn-mini" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить контакт' }}</button></div>
      </form>
      <div class="flex flex-wrap justify-between gap-3 mt-4 text-xs"><label v-if="items.some(c => !c.is_active)" class="inline-flex gap-2 items-center muted"><input v-model="showInactive" type="checkbox" />Показать неактивных</label><button type="button" class="workspace-link" :aria-expanded="showHistory" @click="showHistory = !showHistory">История изменений</button></div>
      <div v-if="showHistory" class="contact-history">
        <p v-if="historyLoading" class="muted text-xs">Загрузка истории…</p><p v-else-if="historyError" class="request-error">{{ historyError }}</p>
        <ol v-else-if="history.length" aria-label="Последние изменения"><li v-for="entry in history" :key="entry.id"><strong>{{ labels[entry.field_name] || entry.field_name }}</strong>: {{ historyValue(entry.old_value) }} → {{ historyValue(entry.new_value) }}<p class="muted text-xs">{{ entry.author_name || 'Менеджер' }} · {{ new Date(entry.changed_at).toLocaleString('ru-RU') }}</p></li></ol><p v-else class="muted text-xs">Изменений пока нет.</p>
      </div>
    </template>
  </section>
</template>

<style scoped src="../../styles/customer-workspace.css"></style>
<style scoped>
.contact-row { padding: 12px 0; border-bottom: 1px solid var(--mv-border); }
.contact-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 14px; }
.contact-links { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 7px; }
.contact-links a { display: inline-flex; align-items: center; gap: 6px; color: var(--kitlane-accent-text); font-size: 13px; overflow-wrap: anywhere; min-width: 0; }
.contact-links a[href^="tel"] { white-space: nowrap; }
.contact-form { margin-top: 12px; padding: 14px; background: var(--mv-bg); border-radius: 9px; }
.contact-history { margin-top: 12px; border-top: 1px solid var(--mv-border); padding-top: 10px; }
.contact-history li { margin: 10px 0; font-size: 13px; overflow-wrap: anywhere; }
.inactive { opacity: .65; }
</style>
