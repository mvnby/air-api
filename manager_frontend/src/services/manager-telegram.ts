import { OpenAPI, type TelegramChallengeResponse, type TelegramChallengeStartResponse } from '../client';
import { request } from '../client/core/request';

export type TelegramChallenge = TelegramChallengeResponse;
export type TelegramChallengeStart = TelegramChallengeStartResponse;
const headers = { 'X-Kitlane-Telegram': '1' };
const linkPath = '/api/manager/account/telegram/link-challenges';
const loginPath = '/login/telegram/challenges';
const idPath = (path: string, id: string) => `${path}/${encodeURIComponent(id)}`;
export const managerTelegramApi = {
  startLink: () => request<TelegramChallengeStart>(OpenAPI, { method: 'POST', url: linkPath, headers }),
  linkStatus: (id: string) => request<TelegramChallenge>(OpenAPI, { method: 'GET', url: idPath(linkPath, id) }),
  confirmLink: (id: string, telegram_id: number) => request(OpenAPI, { method: 'POST', url: `${idPath(linkPath, id)}/confirm`, headers, body: { telegram_id }, mediaType: 'application/json' }),
  disconnect: (current_password: string) => request<void>(OpenAPI, { method: 'DELETE', url: '/api/manager/account/telegram', headers, body: { current_password }, mediaType: 'application/json' }),
  startLogin: () => request<TelegramChallengeStart>(OpenAPI, { method: 'POST', url: loginPath, headers }),
  loginStatus: (id: string) => request<TelegramChallenge>(OpenAPI, { method: 'GET', url: idPath(loginPath, id) }),
  completeLogin: (id: string) => request(OpenAPI, { method: 'POST', url: `${idPath(loginPath, id)}/complete`, headers }),
};
export const safeTelegramDeepLink = (value: string): string | null => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 't.me' && Boolean(url.pathname.slice(1)) ? url.href : null;
  } catch { return null; }
};
