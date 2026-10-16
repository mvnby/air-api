<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { managerTelegramApi, safeTelegramDeepLink } from '../../services/manager-telegram';
import { useTelegramChallenge } from '../../composables/useTelegramChallenge';
const props = defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ authenticated: []; busy: [value: boolean] }>();
let active = true;
let completion: ReturnType<typeof managerTelegramApi.completeLogin> | null = null;
const completing = ref(false);
const { challenge, loading, error, start, reset, retry } = useTelegramChallenge({
  start: managerTelegramApi.startLogin, status: managerTelegramApi.loginStatus, readyStatus: 'approved',
  ready: async result => {
    if (props.disabled || !active) return;
    completing.value = true; emit('busy', true);
    try {
      completion = managerTelegramApi.completeLogin(result.challenge_id);
      await completion;
      if (active) emit('authenticated');
    } catch (cause) { if (active) emit('busy', false); throw cause; }
    finally { completing.value = false; completion = null; }
  },
});
watch(() => props.disabled, value => { if (value) reset(); });
onBeforeUnmount(() => { active = false; completion?.cancel?.(); });
</script>
<template>
  <div class="w-full space-y-3 text-sm">
    <button v-if="!challenge" type="button" class="w-full rounded-lg border border-gray-300 px-4 py-2.5 font-semibold text-brand-700 disabled:opacity-50 dark:border-slate-600 dark:text-brand-300" :disabled="loading || disabled" @click="start">{{ loading ? 'Готовим вход…' : 'Войти через Telegram' }}</button>
    <template v-else>
      <template v-if="!['expired', 'denied', 'completed'].includes(challenge.status)">
        <p>Откройте бота и подтвердите вход. Код в боте должен совпасть с этим:</p>
        <p class="rounded-lg bg-gray-100 px-4 py-3 text-center font-mono text-2xl font-bold tracking-[0.22em] dark:bg-slate-800" aria-label="Код подтверждения входа">{{ challenge.browser_code }}</p>
        <a :href="safeTelegramDeepLink(challenge.deep_link) || undefined" target="_blank" rel="noopener noreferrer" class="block rounded-lg bg-brand-600 px-4 py-2.5 text-center font-semibold text-white">Открыть Telegram</a>
        <p role="status" class="text-gray-500 dark:text-slate-400">{{ completing ? 'Завершаем вход…' : 'Ждём подтверждения в Telegram…' }}</p>
      </template>
      <p v-else role="status">{{ challenge.status === 'denied' ? 'Вход отклонён в Telegram.' : challenge.status === 'expired' ? 'Время для входа истекло.' : 'Вход подтверждён.' }}</p>
      <button type="button" class="text-gray-500 underline" :disabled="completing" @click="reset">{{ ['expired', 'denied'].includes(challenge.status) ? 'Начать заново' : 'Отмена' }}</button>
    </template>
    <p v-if="error" role="alert" class="text-red-700 dark:text-red-300">{{ error }} <button v-if="challenge" type="button" class="underline" @click="retry">Повторить</button></p>
  </div>
</template>
