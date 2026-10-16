import { onBeforeUnmount, ref } from 'vue';
import { getApiErrorMessage } from '../utils/api-errors';
import { safeTelegramDeepLink, type TelegramChallenge, type TelegramChallengeStart } from '../services/manager-telegram';

export const useTelegramChallenge = (options: {
  start: () => PromiseLike<TelegramChallengeStart>;
  status: (id: string) => PromiseLike<TelegramChallenge>;
  ready: (challenge: TelegramChallenge) => Promise<void> | void;
  readyStatus: 'claimed' | 'approved';
}) => {
  const challenge = ref<TelegramChallengeStart | null>(null);
  const loading = ref(false);
  const error = ref('');
  let timer: ReturnType<typeof setTimeout> | undefined;
  let version = 0;
  const stop = () => { version++; if (timer) clearTimeout(timer); timer = undefined; };
  const reset = () => { stop(); challenge.value = null; error.value = ''; loading.value = false; };
  const poll = async (generation: number) => {
    if (generation !== version || !challenge.value) return;
    if (Date.parse(challenge.value.expires_at) <= Date.now()) { challenge.value.status = 'expired'; return; }
    try {
      const result = await options.status(challenge.value.challenge_id);
      if (generation !== version || !challenge.value) return;
      challenge.value = { ...challenge.value, ...result };
      if (result.status === options.readyStatus) { await options.ready(result); return; }
      if (['expired', 'canceled', 'confirmed', 'denied', 'completed'].includes(result.status)) return;
      timer = setTimeout(() => { void poll(generation); }, 2000);
    } catch (cause) {
      if (generation === version) error.value = getApiErrorMessage(cause);
    }
  };
  const start = async () => {
    reset(); const generation = version; loading.value = true;
    try {
      const result = await options.start();
      if (generation !== version) return;
      if (!safeTelegramDeepLink(result.deep_link)) throw new Error('Сервер вернул некорректную ссылку Telegram.');
      challenge.value = result;
      timer = setTimeout(() => { void poll(generation); }, 1500);
    } catch (cause) { if (generation === version) error.value = getApiErrorMessage(cause); }
    finally { if (generation === version) loading.value = false; }
  };
  const retry = () => { error.value = ''; void poll(version); };
  onBeforeUnmount(stop);
  return { challenge, loading, error, start, reset, retry, stop };
};
