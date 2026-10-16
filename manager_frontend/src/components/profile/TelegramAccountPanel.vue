<script setup lang="ts">
import { computed, ref } from 'vue';
import type { OwnProfile } from '../../services/manager-profile';
import { managerProfileApi, refreshManagerIdentity } from '../../services/manager-profile';
import { managerTelegramApi, safeTelegramDeepLink } from '../../services/manager-telegram';
import { managerSession } from '../../services/manager-session';
import { useTelegramChallenge } from '../../composables/useTelegramChallenge';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ profile: OwnProfile; disabled?: boolean }>();
const emit = defineEmits<{ updated: [profile: OwnProfile] }>();
const saving = ref(false);
const actionError = ref('');
const disconnectOpen = ref(false);
const password = ref('');
const canDisconnect = computed(() => Boolean(props.profile.username && managerSession.auth.value?.can_change_password));
const { challenge, loading, error, start, reset, retry, stop } = useTelegramChallenge({ start: managerTelegramApi.startLink, status: managerTelegramApi.linkStatus, readyStatus: 'claimed', ready: () => {} });
const busy = computed(() => props.disabled || saving.value);
const refresh = async () => {
  await refreshManagerIdentity();
  emit('updated', await managerProfileApi.get());
};
const confirm = async () => {
  const candidate = challenge.value?.telegram;
  if (!candidate || !challenge.value || busy.value) return;
  saving.value = true; actionError.value = '';
  try { await managerTelegramApi.confirmLink(challenge.value.challenge_id, candidate.id); reset(); await refresh(); }
  catch (cause) { actionError.value = getApiErrorMessage(cause); }
  finally { saving.value = false; }
};
const disconnect = async () => {
  if (!password.value || busy.value || !canDisconnect.value) return;
  saving.value = true; actionError.value = '';
  try { await managerTelegramApi.disconnect(password.value); password.value = ''; disconnectOpen.value = false; await refresh(); }
  catch (cause) { actionError.value = getApiErrorMessage(cause); }
  finally { saving.value = false; }
};
const notifications = async (event: Event) => {
  const input = event.target as HTMLInputElement;
  const enabled = input.checked;
  input.checked = props.profile.telegram_notifications_enabled;
  if (busy.value || !props.profile.telegram_linked) return;
  saving.value = true; actionError.value = '';
  try { emit('updated', await managerProfileApi.update({ telegram_notifications_enabled: enabled, expected_updated_at: props.profile.updated_at })); }
  catch (cause) { actionError.value = getApiErrorMessage(cause); }
  finally { saving.value = false; }
};
const cancel = () => { stop(); reset(); actionError.value = ''; };
</script>
<template>
  <section class="mt-6 border-t border-gray-200 pt-5 dark:border-slate-700">
    <h2 class="font-semibold text-gray-900 dark:text-white">Telegram</h2>
    <template v-if="profile.telegram_linked">
      <p class="mt-2 text-sm text-gray-600 dark:text-slate-300">Подключён<span v-if="profile.telegram_username">: @{{ profile.telegram_username }}</span></p>
      <label class="mt-3 flex cursor-pointer items-center gap-3 text-sm"><input type="checkbox" role="switch" aria-label="Уведомления Telegram" :checked="profile.telegram_notifications_enabled" :disabled="busy" @change="notifications" /><span>Получать рабочие уведомления в Telegram</span></label>
      <button v-if="!disconnectOpen" type="button" class="mt-3 text-sm text-gray-500 underline disabled:opacity-50" :disabled="busy || !canDisconnect" @click="disconnectOpen = true; actionError = ''">Отключить Telegram</button>
      <p v-if="!canDisconnect" class="mt-2 text-xs text-gray-500">Для отключения нужен доступ по логину и паролю.</p>
      <form v-if="disconnectOpen" class="mt-3 space-y-3 rounded-lg border border-gray-200 p-3 dark:border-slate-700" @submit.prevent="disconnect">
        <p class="text-sm text-gray-600 dark:text-slate-300">Подтвердите пароль Kitlane. После отключения вход через Telegram будет недоступен.</p>
        <label class="block text-sm">Пароль Kitlane<input v-model="password" type="password" autocomplete="current-password" required class="mt-1 block w-full rounded-lg border bg-transparent px-3 py-2" /></label>
        <div class="flex gap-3"><button type="submit" class="rounded-lg border px-3 py-2 text-sm font-semibold" :disabled="busy || !password">Отключить</button><button type="button" class="text-sm text-gray-500" :disabled="busy" @click="disconnectOpen = false; password = ''">Отмена</button></div>
      </form>
    </template>
    <template v-else>
      <p class="mt-2 text-sm text-gray-600 dark:text-slate-300">Подключите свой аккаунт для входа и рабочих уведомлений.</p>
      <button v-if="!challenge" type="button" class="mt-3 rounded-lg border border-gray-300 px-3 py-2 text-sm font-semibold disabled:opacity-50 dark:border-slate-600" :disabled="busy || loading" @click="start">{{ loading ? 'Готовим подключение…' : 'Подключить Telegram' }}</button>
      <div v-else class="mt-3 space-y-3 rounded-lg bg-gray-50 p-4 dark:bg-slate-800">
        <template v-if="challenge.status === 'claimed' && challenge.telegram">
          <p class="text-sm">Подключить этот аккаунт?</p><p class="font-semibold">{{ challenge.telegram.display_name }}<span v-if="challenge.telegram.username" class="block text-sm font-normal text-gray-500">@{{ challenge.telegram.username }}</span></p>
          <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="busy" @click="confirm">Подтвердить подключение</button>
        </template>
        <p v-else-if="['expired', 'canceled'].includes(challenge.status)" role="status" class="text-sm">Время подключения истекло. Начните заново.</p>
        <template v-else><a :href="safeTelegramDeepLink(challenge.deep_link) || undefined" target="_blank" rel="noopener noreferrer" class="inline-flex rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white">Открыть Telegram</a><p role="status" class="text-sm text-gray-500">Нажмите «Начать» в боте, затем подтвердите аккаунт здесь.</p></template>
        <button type="button" class="ml-3 text-sm text-gray-500 underline" :disabled="busy" @click="cancel">{{ ['expired', 'canceled'].includes(challenge.status) ? 'Начать заново' : 'Отмена' }}</button>
      </div>
    </template>
    <p v-if="saving" role="status" class="mt-3 text-sm text-gray-500">Сохраняем…</p>
    <p v-if="actionError || error" role="alert" class="mt-3 text-sm text-red-700 dark:text-red-300">{{ actionError || error }} <button v-if="error && challenge" type="button" class="underline" @click="retry">Повторить</button></p>
  </section>
</template>
