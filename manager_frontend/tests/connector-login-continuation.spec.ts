import { describe, expect, it, vi } from 'vitest';
import { connectorLoginContinuation, resumeConnectorLogin } from '../src/services/connector-login-continuation';
import type { ManagerAuthStatusResponse } from '../src/client';

const origin = 'https://api.mvn.by';
const target = '/api/connector/oauth/authorize?' + new URLSearchParams({
  client_id: 'kitlane-chatgpt', state: 'saved-state', code_challenge: 'challenge',
  code_challenge_method: 'S256', response_type: 'code',
  redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect',
  resource: origin + '/api/connector/mcp', scope: 'kitlane:read',
});
const search = (value: string) => '?' + new URLSearchParams({ connector_return: value });
const auth: ManagerAuthStatusResponse = { username: 'manager', status: 'authenticated', staff_user_id: 4, auth_source: 'staff' };

describe('resume a personal Kitlane connection after login', () => {
  it('preserves the valid local authorization request and state', () => {
    const next = connectorLoginContinuation(search(target), origin);
    expect(next).toBe(target);
    const navigate = vi.fn();
    expect(resumeConnectorLogin(next, auth, navigate)).toBe(true);
    expect(navigate).toHaveBeenCalledWith(target);
  });
  it.each(['https://evil.example/' + target, '//evil.example', '/manager/profile',
    target + '#fragment', target + '\\evil', target + '\n',
    '/api/connector/oauth/authorize/../token?state=x',
    target + '&client_id=attacker', target.replace('kitlane-chatgpt', 'attacker'),
    target.replace('S256', 'plain'), 'x'.repeat(8193),
  ])('rejects an unsafe continuation %s', value => {
    expect(connectorLoginContinuation(search(value), origin)).toBeNull();
  });
  it('rejects duplicate continuation parameters', () => {
    expect(connectorLoginContinuation(search(target) + '&connector_return=' + encodeURIComponent(target), origin)).toBeNull();
  });
  it.each([null, { ...auth, staff_user_id: undefined }, { ...auth, auth_source: 'legacy' }, { ...auth, must_change_password: true }])('waits for a usable named account', account => {
    const navigate = vi.fn();
    expect(resumeConnectorLogin(target, account, navigate)).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });
});
