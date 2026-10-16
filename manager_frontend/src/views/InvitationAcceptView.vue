<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { managerInvitationsApi, teamRoles, type InvitationPreview, type InvitationAccept } from '../services/manager-invitations';
import { managerCompaniesApi } from '../services/manager-companies';
import { passwordPolicyMessage } from '../services/manager-account-security';
import { getApiErrorMessage } from '../utils/api-errors';
const props = defineProps<{ token: string; navigateAfterAccept?: (url: string) => void }>();
const preview = ref<InvitationPreview | null>(null), loading = ref(true), error = ref(''), busy = ref(false);
const existingName = ref(''), mode = ref<'existing' | 'new' | 'existing_credentials' | null>(null);
const username = ref(''), password = ref(''), displayName = ref('');
const expired = computed(() => !!preview.value && Date.parse(preview.value.expires_at) <= Date.now());
onMounted(async () => {
  if (!props.token) { error.value = 'В ссылке нет приглашения. Попросите владельца прислать новую ссылку.'; loading.value = false; return; }
  const identity = managerCompaniesApi.choices().then(result => { existingName.value = result.username; }).catch(() => {});
  try { preview.value = await managerInvitationsApi.preview(props.token); } catch (e) { error.value = getApiErrorMessage(e) || 'Приглашение недействительно или уже использовано'; }
  finally { loading.value = false; }
  await identity;
});
const accept = async () => {
  if (!preview.value || !mode.value || busy.value || expired.value) return;
  error.value = '';
  if (mode.value === 'new') { const policy = passwordPolicyMessage(password.value); if (policy) { error.value = policy; return; } }
  let body: InvitationAccept;
  if (mode.value === 'existing') body = { token: props.token, mode: 'existing' };
  else if (mode.value === 'new') body = { token: props.token, mode: 'new', username: username.value.trim(), password: password.value, display_name: displayName.value.trim() };
  else body = { token: props.token, mode: 'existing_credentials', username: username.value.trim(), password: password.value };
  busy.value = true;
  try {
    const accepted = await managerInvitationsApi.accept(body);
    password.value = '';
    const query = new URLSearchParams({ company: String(accepted.tenant_id) });
    if (accepted.default_storefront_slug) query.set('site', accepted.default_storefront_slug);
    const url = `/manager/?${query}`;
    if (props.navigateAfterAccept) props.navigateAfterAccept(url); else window.location.assign(url);
  } catch (e) { error.value = getApiErrorMessage(e) || 'Не удалось принять приглашение'; }
  finally { busy.value = false; }
};
</script>
<template>
  <main class="flex min-h-screen items-center justify-center bg-slate-50 p-4 sm:p-8">
    <section class="w-full max-w-lg space-y-5 rounded-2xl border bg-white p-6 shadow-sm sm:p-8" aria-labelledby="invitation-title">
      <div class="text-sm font-bold uppercase tracking-widest text-brand-700">Kitlane</div>
      <h1 id="invitation-title" class="text-2xl font-bold text-slate-900">Приглашение в компанию</h1>
      <p v-if="loading" role="status" class="text-gray-500">Проверяем приглашение…</p>
      <template v-if="preview"><p class="text-gray-600">Компания <strong class="text-gray-900">{{ preview.company_name }}</strong> приглашает вас с ролью «{{ teamRoles[preview.role] }}».</p><p class="text-sm text-gray-500">Действует до {{ new Date(preview.expires_at).toLocaleString('ru-RU') }}</p>
        <form v-if="!expired" class="space-y-4" @submit.prevent="accept">
          <fieldset :disabled="busy" class="space-y-2"><legend class="mb-2 text-sm font-semibold">Как присоединиться</legend>
            <label v-if="existingName" class="flex gap-3 rounded-lg border p-3 text-sm"><input v-model="mode" type="radio" value="existing" name="join-mode" class="mt-0.5" /><span>Использовать текущий аккаунт <strong>{{ existingName }}</strong></span></label>
            <label class="flex gap-3 rounded-lg border p-3 text-sm"><input v-model="mode" type="radio" value="existing_credentials" name="join-mode" class="mt-0.5" /><span>Войти в существующий аккаунт</span></label>
            <label class="flex gap-3 rounded-lg border p-3 text-sm"><input v-model="mode" type="radio" value="new" name="join-mode" class="mt-0.5" /><span>Создать личный аккаунт</span></label>
          </fieldset>
          <fieldset v-if="mode && mode !== 'existing'" :disabled="busy" class="space-y-3">
            <label v-if="mode === 'new'" class="block text-sm font-medium">Ваше имя<input v-model="displayName" required maxlength="160" autocomplete="name" class="mt-1 w-full rounded-lg border px-3 py-2.5" /></label>
            <label class="block text-sm font-medium">Логин<input v-model="username" required maxlength="100" autocomplete="username" autocapitalize="none" class="mt-1 w-full rounded-lg border px-3 py-2.5" /></label>
            <label class="block text-sm font-medium">Пароль<input v-model="password" type="password" required :autocomplete="mode === 'new' ? 'new-password' : 'current-password'" class="mt-1 w-full rounded-lg border px-3 py-2.5" /></label>
            <p v-if="mode === 'new'" class="text-xs text-gray-500">Не менее 9 символов.</p>
          </fieldset>
          <button class="w-full rounded-lg bg-brand-600 px-4 py-3 font-semibold text-white disabled:opacity-50" :disabled="!mode || busy">{{ busy ? 'Присоединяемся…' : 'Принять приглашение' }}</button>
        </form>
        <p v-else class="text-amber-700">Срок приглашения истёк. Попросите владельца создать новое.</p>
      </template>
      <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
    </section>
  </main>
</template>
