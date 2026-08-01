import { ref, shallowRef } from 'vue';

import {
  LoginService,
  ManagerService,
  type ManagerAuthStatusResponse,
  type TelegramLoginPayload,
} from '../client';
import { managerStorefrontSelection } from './manager-storefront-selection';

type AuthenticationStep = () => PromiseLike<unknown>;

export const managerSession = {
  isAuthenticated: ref(false),
  currentUserRole: ref(''),
  auth: shallowRef<ManagerAuthStatusResponse | null>(null),
  bootstrapping: ref(false),
  recoveryRequired: ref(false),
};

export const clearManagerSession = (): void => {
  managerStorefrontSelection.prepareAuthentication();
  managerSession.isAuthenticated.value = false;
  managerSession.currentUserRole.value = '';
  managerSession.auth.value = null;
  managerSession.bootstrapping.value = false;
  managerSession.recoveryRequired.value = false;
};

export const requireManagerSessionRecovery = (): void => {
  clearManagerSession();
  managerSession.recoveryRequired.value = true;
};

export const bootstrapManagerSession = async (
  authenticate?: AuthenticationStep,
): Promise<ManagerAuthStatusResponse> => {
  managerSession.bootstrapping.value = true;
  managerSession.isAuthenticated.value = false;
  managerSession.currentUserRole.value = '';
  managerSession.auth.value = null;
  managerStorefrontSelection.prepareAuthentication();

  try {
    if (authenticate) await authenticate();
    const auth = await ManagerService.readUserMe();
    await managerStorefrontSelection.initialize(auth);
    managerSession.auth.value = auth;
    managerSession.currentUserRole.value = String(auth.role || '');
    managerSession.isAuthenticated.value = true;
    return auth;
  } finally {
    managerSession.bootstrapping.value = false;
  }
};

export const loginManagerWithPassword = (
  username: string,
  password: string,
): Promise<ManagerAuthStatusResponse> => bootstrapManagerSession(
  () => LoginService.loginAccessToken({ username, password }),
);

export const loginManagerWithTelegram = (
  payload: TelegramLoginPayload,
): Promise<ManagerAuthStatusResponse> => bootstrapManagerSession(
  () => LoginService.loginTelegram(payload),
);

export const restoreManagerSession = (): Promise<ManagerAuthStatusResponse> => (
  bootstrapManagerSession()
);
