import { OpenAPI, type ManagerStaffResponse, type ManagerStaffInvitationItem, type StaffInvitationPreview, type StaffInvitationAcceptExisting, type StaffInvitationAcceptNew, type StaffInvitationAcceptCredentials } from '../client';
import { request } from '../client/core/request';
export const teamRoles = { owner: 'Владелец', admin: 'Администратор', manager: 'Менеджер', catalog_editor: 'Редактор каталога', installer: 'Монтажник' } as const;
export type InviteRole = keyof typeof teamRoles;
export type TeamInvitation = ManagerStaffInvitationItem;
export type InvitationPreview = StaffInvitationPreview;
export type InvitationAccept = StaffInvitationAcceptExisting | StaffInvitationAcceptNew | StaffInvitationAcceptCredentials;
const headers = { 'X-Kitlane-Team': '1' };
const url = '/api/manager/staff/invitations';
export const managerInvitationsApi = {
  list: (page = 1) => request<{ items: TeamInvitation[]; total: number; page: number; limit: number }>(OpenAPI, { method: 'GET', url, query: { page, limit: 50 } }),
  create: (role: InviteRole) => request<{ id: number; role: InviteRole; expires_at: string; invite_url: string }>(OpenAPI, { method: 'POST', url, headers, body: { role }, mediaType: 'application/json' }),
  revoke: (id: number) => request<void>(OpenAPI, { method: 'DELETE', url: `${url}/${id}`, headers }),
  updateMember: (id: number, body: { primary_role?: string; status?: string; can_manage_worker_money?: boolean; can_manage_worker_pay?: boolean }) => request<ManagerStaffResponse>(OpenAPI, { method: 'PATCH', url: `/api/manager/staff/${id}`, headers, body, mediaType: 'application/json' }),
  preview: (token: string) => request<InvitationPreview>(OpenAPI, { method: 'POST', url: '/api/account/invitations/preview', headers, body: { token }, mediaType: 'application/json' }),
  accept: (body: InvitationAccept) => request<{ tenant_id: number; default_storefront_slug: string | null }>(OpenAPI, { method: 'POST', url: '/api/account/invitations/accept', headers, body, mediaType: 'application/json' }),
};
