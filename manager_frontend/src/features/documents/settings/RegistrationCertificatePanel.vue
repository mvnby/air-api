<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { managerSession } from '../../../services/manager-session';
import { certificateRequest, downloadCertificate, listCertificates, type RegistrationCertificate } from '../registration-certificates';
const props = defineProps<{ legalEntityId: number }>();
const items = ref<RegistrationCertificate[]>([]);
const busy = ref(false);
const error = ref('');
const canEdit = computed(() => ['owner', 'admin'].includes(managerSession.auth.value?.role || managerSession.currentUserRole.value));
let requestId = 0;
async function load() {
  const id = ++requestId; items.value = []; error.value = '';
  try { const result = await listCertificates(props.legalEntityId); if (id === requestId) items.value = result; }
  catch (err) { if (id === requestId) error.value = String((err as Error).message); }
}
watch(() => props.legalEntityId, load, { immediate: true });
async function upload(event: Event) {
  const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return;
  if (file.size > 10 * 1024 * 1024) { error.value = 'Файл должен быть не больше 10 МБ'; input.value = ''; return; }
  const entityId = props.legalEntityId; busy.value = true; error.value = '';
  try { const body = new FormData(); body.append('file', file); await certificateRequest(`/api/manager/document-system/legal-entities/${entityId}/registration-certificates`, 'POST', body); if (entityId === props.legalEntityId) await load(); }
  catch (err) { error.value = (err as Error).message; }
  finally { busy.value = false; input.value = ''; }
}
async function select(item: RegistrationCertificate) {
  busy.value = true; error.value = '';
  try { await certificateRequest(`/api/manager/document-system/registration-certificates/${item.id}/current`, 'PUT'); await load(); }
  catch (err) { error.value = (err as Error).message; }
  finally { busy.value = false; }
}
async function download(item: RegistrationCertificate) {
  try { await downloadCertificate(item); } catch (err) { error.value = (err as Error).message; }
}
</script>
<template>
  <section class="rounded-xl border border-slate-200 p-4 dark:border-slate-700 sm:col-span-2">
    <h4 class="font-semibold">Свидетельство о регистрации</h4>
    <p class="mt-1 text-sm text-slate-500">PDF, JPEG или PNG до 10 МБ. В письмо добавляется только по вашему выбору. Предыдущие версии сохраняются.</p>
    <label v-if="canEdit" class="settings-button-secondary mt-2 inline-flex cursor-pointer">
      <input type="file" class="hidden" accept="application/pdf,image/jpeg,image/png" :disabled="busy" @change="upload" />
      {{ busy ? 'Сохранение…' : 'Загрузить свидетельство' }}
    </label>
    <p v-if="!items.length" class="mt-2 text-sm text-slate-500">Свидетельство пока не загружено</p>
    <ul class="mt-2 space-y-2">
      <li v-for="item in items" :key="item.id" class="flex flex-wrap items-center gap-2 text-sm">
        <span>{{ item.filename }}</span><span v-if="item.is_current" class="font-semibold text-green-700">Текущая версия</span>
        <button type="button" class="settings-button-secondary" @click="download(item)">Скачать</button>
        <button v-if="canEdit && !item.is_current" type="button" class="settings-button-secondary" :disabled="busy" @click="select(item)">Сделать текущей</button>
      </li>
    </ul>
    <p v-if="error" class="mt-2 text-sm text-red-600">{{ error }}</p>
  </section>
</template>
