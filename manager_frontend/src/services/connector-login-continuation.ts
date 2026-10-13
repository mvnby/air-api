import type { ManagerAuthStatusResponse } from '../client';

const AUTHORIZE_PATH = '/api/connector/oauth/authorize';

export const connectorLoginContinuation = (search: string, origin: string): string | null => {
  const values = new URLSearchParams(search).getAll('connector_return');
  if (values.length !== 1) return null;
  const target = values[0];
  if (!target || target.length > 8192 || /[\\\x00-\x20\x7f#]/.test(target)
    || !target.startsWith(`${AUTHORIZE_PATH}?`)) return null;
  try {
    const url = new URL(target, origin);
    if (url.origin !== origin || url.pathname !== AUTHORIZE_PATH || url.hash) return null;
    const params = url.searchParams;
    if (!params.get('state') || !params.get('code_challenge')
      || params.get('client_id') !== 'kitlane-chatgpt'
      || params.get('response_type') !== 'code'
      || params.get('code_challenge_method') !== 'S256'
      || [...params.keys()].some(key => params.getAll(key).length !== 1)) return null;
    return url.pathname + url.search;
  } catch { return null; }
};

export const resumeConnectorLogin = (
  target: string | null,
  auth: ManagerAuthStatusResponse | null,
  navigate: (path: string) => void = path => window.location.replace(path),
): boolean => {
  if (!target || !auth?.staff_user_id || auth.auth_source === 'legacy' || auth.must_change_password) return false;
  navigate(target);
  return true;
};
