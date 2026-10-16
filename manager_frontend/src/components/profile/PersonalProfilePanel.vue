<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { registerUnsavedNavigationGuard } from '../../services/unsaved-navigation-guard';
import { confirmDialog } from '../../services/ui-feedback';
import PersonAvatar from '../common/PersonAvatar.vue';
import AvatarCropDialog from './AvatarCropDialog.vue';
import TelegramAccountPanel from './TelegramAccountPanel.vue';
import { applyOwnProfile, managerProfileApi, type OwnProfile } from '../../services/manager-profile';
import { managerSession } from '../../services/manager-session';
import { getApiErrorMessage } from '../../utils/api-errors';
const profile = ref<OwnProfile | null>(null);
const loading = ref(true);
const personalReadOnly = computed(() => profile.value?.personal_read_only === true);
const saving = ref(false);
const avatarSaving = ref(false);
const error = ref('');
const avatarError = ref('');
const success = ref('');
const file = ref<File | null>(null);
const draft = ref({ display_name: '', phone: '', email: '' });
let active = true;
const dirty = computed(() => profile.value && (draft.value.display_name !== profile.value.display_name || draft.value.phone !== (profile.value.phone || '') || draft.value.email !== (profile.value.email || '')));
const unregisterGuard = registerUnsavedNavigationGuard(async () => {
  if (saving.value || avatarSaving.value) return false;
  return !dirty.value && !file.value || await confirmDialog({ title: 'Покинуть профиль?', description: 'Изменения личных данных ещё не сохранены.', confirmText: 'Покинуть' });
});
const editable = computed(() => Boolean(managerSession.auth.value?.staff_user_id && managerSession.auth.value?.auth_source !== 'legacy'));
const accept = (value: OwnProfile, resetDraft = false) => {
  if (!active || value.staff_user_id !== managerSession.auth.value?.staff_user_id) return;
  profile.value = value; applyOwnProfile(value);
  if (resetDraft) draft.value = { display_name: value.display_name, phone: value.phone || '', email: value.email || '' };
};
const load = async () => {
  if (!editable.value) { loading.value = false; return; }
  loading.value = true; error.value = '';
  try { accept(await managerProfileApi.get(), true); }
  catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { loading.value = false; }
};
const save = async () => {
  if (!profile.value || saving.value || avatarSaving.value || personalReadOnly.value) return;
  saving.value = true; error.value = ''; success.value = '';
  try {
    accept(await managerProfileApi.update({ display_name: draft.value.display_name.trim(), phone: draft.value.phone.trim() || null, email: draft.value.email.trim() || null, expected_updated_at: profile.value.updated_at }), true);
    success.value = 'Профиль сохранён';
  } catch (cause) { error.value = getApiErrorMessage(cause); }
  finally { saving.value = false; }
};
const selectFile = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const selected = input.files?.[0]; input.value = ''; avatarError.value = '';
  if (!selected || personalReadOnly.value) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) { avatarError.value = 'Выберите фото JPEG, PNG или WebP.'; return; }
  if (selected.size > 5 * 1024 * 1024) { avatarError.value = 'Фото не должно превышать 5 МБ.'; return; }
  file.value = selected;
};
const upload = async (prepared: File) => {
  if (!profile.value || avatarSaving.value || personalReadOnly.value) return;
  avatarSaving.value = true; avatarError.value = '';
  try { accept(await managerProfileApi.uploadAvatar(prepared, profile.value.updated_at)); file.value = null; success.value = 'Фото обновлено'; }
  catch (cause) { avatarError.value = getApiErrorMessage(cause); }
  finally { avatarSaving.value = false; }
};
const remove = async () => {
  if (!profile.value || avatarSaving.value || personalReadOnly.value) return;
  avatarSaving.value = true; avatarError.value = '';
  try { accept(await managerProfileApi.removeAvatar(profile.value.updated_at)); success.value = 'Фото удалено'; }
  catch (cause) { avatarError.value = getApiErrorMessage(cause); }
  finally { avatarSaving.value = false; }
};
onMounted(load);
onBeforeUnmount(() => { active = false; unregisterGuard(); });
</script>
<template>
  <section class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900 sm:p-6" aria-labelledby="personal-profile-title">
    <h2 id="personal-profile-title" class="text-lg font-semibold text-gray-900 dark:text-white">Личные данные</h2>
    <p v-if="!editable" class="mt-3 text-sm text-gray-600">Редактирование профиля доступно после входа в личную учётную запись.</p>
    <p v-else-if="loading" role="status" class="mt-4 text-sm text-gray-500">Загрузка профиля…</p>
    <template v-else-if="profile"><p v-if="personalReadOnly" class="mt-3 text-sm text-amber-700">Личный профиль доступен только для просмотра.</p>
      <div class="mt-5 flex flex-wrap items-center gap-4">
        <PersonAvatar :name="profile.display_name" :src="profile.avatar_url" size="lg" />
        <div class="space-y-2"><label class="inline-flex cursor-pointer rounded-lg border border-gray-300 px-3 py-2 text-sm font-semibold dark:border-slate-600" :class="saving || avatarSaving || personalReadOnly ? 'pointer-events-none opacity-50' : ''">Изменить фото<input type="file" accept="image/jpeg,image/png,image/webp" aria-label="Загрузить фото профиля" class="sr-only" :disabled="saving || avatarSaving || personalReadOnly" @change="selectFile" /></label><button v-if="profile.avatar_url" type="button" class="ml-3 text-sm text-gray-500 underline" :disabled="saving || avatarSaving || personalReadOnly" @click="remove">Удалить фото</button><p class="text-xs text-gray-500">JPEG, PNG или WebP · до 5 МБ</p></div>
      </div>
      <p v-if="avatarError && !file" role="alert" class="mt-3 text-sm text-red-700">{{ avatarError }}</p>
      <form class="mt-5 space-y-4" data-testid="personal-profile-form" @submit.prevent="save">
        <label class="block text-sm font-medium">Имя<input v-model="draft.display_name" required maxlength="160" autocomplete="name" class="mt-1 block w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-slate-600" :disabled="saving || personalReadOnly" /></label>
        <label class="block text-sm font-medium">Логин<input :value="profile.username || 'Логин не задан'" readonly aria-readonly="true" class="mt-1 block w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-gray-500 dark:border-slate-700 dark:bg-slate-800" /><span class="mt-1 block text-xs font-normal text-gray-500">Логин используется для входа и здесь не меняется.</span></label>
        <div class="grid gap-4 sm:grid-cols-2"><label class="block text-sm font-medium">Телефон<input v-model="draft.phone" type="tel" autocomplete="tel" maxlength="80" class="mt-1 block w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-slate-600" :disabled="saving || personalReadOnly" /></label><label class="block text-sm font-medium">Email<input v-model="draft.email" type="email" autocomplete="email" maxlength="254" class="mt-1 block w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-slate-600" :disabled="saving || personalReadOnly" /></label></div>
        <p class="text-xs text-gray-500">Личные данные общие для всех ваших компаний.</p>
        <button type="submit" class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="saving || avatarSaving || personalReadOnly || !draft.display_name.trim()">{{ saving ? 'Сохраняем…' : 'Сохранить профиль' }}</button>
      </form>
      <TelegramAccountPanel :profile="profile" :disabled="saving || avatarSaving || personalReadOnly" @updated="accept($event)" />
    </template>
    <p v-if="error" role="alert" class="mt-4 text-sm text-red-700 dark:text-red-300">{{ error }} <button type="button" class="underline" @click="load">Обновить профиль</button></p>
    <p v-if="success" role="status" class="mt-3 text-sm text-emerald-700 dark:text-emerald-300">{{ success }}</p>
    <AvatarCropDialog :file="file" :busy="avatarSaving" :error-message="avatarError" @close="file = null; avatarError = ''" @save="upload" />
  </section>
</template>
