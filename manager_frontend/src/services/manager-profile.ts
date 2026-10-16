import { shallowRef, watch } from 'vue';
import { ManagerService, OpenAPI, type ManagerOwnProfileResponse, type ManagerOwnProfileUpdate } from '../client';
import { request } from '../client/core/request';
import { managerSession } from './manager-session';

export type OwnProfile = ManagerOwnProfileResponse;
export const ownProfileState = shallowRef<OwnProfile | null>(null);
watch(managerSession.auth, auth => { if (!auth || ownProfileState.value?.staff_user_id !== auth.staff_user_id) ownProfileState.value = null; }, { flush: 'sync' });
export type OwnProfileUpdate = ManagerOwnProfileUpdate;
const path = '/api/manager/account/profile';
const headers = { 'X-Kitlane-Profile': '1' };
export const managerProfileApi = {
  get: () => request<OwnProfile>(OpenAPI, { method: 'GET', url: path }),
  update: (body: OwnProfileUpdate) => request<OwnProfile>(OpenAPI, { method: 'PATCH', url: path, headers, body, mediaType: 'application/json' }),
  uploadAvatar: (file: File, expected_updated_at: string) => request<OwnProfile>(OpenAPI, { method: 'POST', url: `${path}/avatar`, headers, formData: { file, expected_updated_at }, mediaType: 'multipart/form-data' }),
  removeAvatar: (expected_updated_at: string) => request<OwnProfile>(OpenAPI, { method: 'DELETE', url: `${path}/avatar`, headers, body: { expected_updated_at }, mediaType: 'application/json' }),
};
export const applyOwnProfile = (profile: OwnProfile) => {
  const auth = managerSession.auth.value;
  if (auth?.staff_user_id !== profile.staff_user_id) return;
  ownProfileState.value = profile;
  managerSession.auth.value = { ...auth, display_name: profile.display_name, avatar_url: profile.avatar_url };
};
export const refreshManagerIdentity = async () => {
  const previous = managerSession.auth.value;
  if (!previous) return;
  const fresh = await ManagerService.readUserMe();
  if (managerSession.auth.value === previous) {
    managerSession.auth.value = { ...fresh };
    managerSession.currentUserRole.value = fresh.role || '';
  }
};
