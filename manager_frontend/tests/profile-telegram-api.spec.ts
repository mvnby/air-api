import { beforeEach, describe, expect, it, vi } from 'vitest';
const requestMock = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock('../src/client/core/request', () => ({ request: requestMock }));
import { managerProfileApi } from '../src/services/manager-profile';
import { managerTelegramApi } from '../src/services/manager-telegram';
describe('personal account request boundaries', () => {
  beforeEach(() => requestMock.mockClear());
  it('sends the profile security header and expected version with every mutation', async () => {
    const file = new File(['image'], 'face.webp', { type: 'image/webp' });
    await managerProfileApi.update({ display_name: 'Name', expected_updated_at: 'v1' }); await managerProfileApi.uploadAvatar(file, 'v2'); await managerProfileApi.removeAvatar('v3');
    expect(requestMock.mock.calls.map(call => call[1])).toEqual([
      expect.objectContaining({ method: 'PATCH', headers: { 'X-Kitlane-Profile': '1' }, body: { display_name: 'Name', expected_updated_at: 'v1' } }),
      expect.objectContaining({ method: 'POST', headers: { 'X-Kitlane-Profile': '1' }, formData: { file, expected_updated_at: 'v2' } }),
      expect.objectContaining({ method: 'DELETE', headers: { 'X-Kitlane-Profile': '1' }, body: { expected_updated_at: 'v3' } }),
    ]);
  });
  it('adds the Telegram header to sensitive commands without browser tokens in payloads', async () => {
    await managerTelegramApi.startLink(); await managerTelegramApi.confirmLink('id', 12); await managerTelegramApi.disconnect('secret'); await managerTelegramApi.startLogin(); await managerTelegramApi.completeLogin('id');
    for (const call of requestMock.mock.calls) expect(call[1].headers).toEqual({ 'X-Kitlane-Telegram': '1' });
    expect(requestMock.mock.calls[1]![1].body).toEqual({ telegram_id: 12 }); expect(requestMock.mock.calls[2]![1].body).toEqual({ current_password: 'secret' });
  });
});
