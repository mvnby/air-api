import {
  OpenAPI, ManagerTenderModuleService,
  type TenderModuleAccess, type TenderModuleEntitlementUpdate, type TenderModuleSettings, type TenderModuleUpdate,
  type TenderProfilePreview, type TenderSearchProfile,
} from '../client';
import { request } from '../client/core/request';

const settingsUrl = '/api/manager/tender-module';
const accessUrl = '/api/manager/platform/companies/{tenant_id}/tender-module';
const headers = { 'X-Kitlane-Team': '1' };

export const tenderModuleApi = {
  get: () => ManagerTenderModuleService.getManagerTenderModule(),
  update: (body: TenderModuleUpdate) => request<TenderModuleSettings>(OpenAPI, {
    method: 'PUT', url: settingsUrl, headers, body, mediaType: 'application/json',
  }),
  preview: (body: TenderSearchProfile) => request<TenderProfilePreview>(OpenAPI, {
    method: 'POST', url: `${settingsUrl}/profile-preview`, headers, body, mediaType: 'application/json',
  }),
  getCompanyAccess: (tenantId: number) => ManagerTenderModuleService.getPlatformCompanyTenderModule(tenantId),
  updateCompanyAccess: (tenantId: number, body: TenderModuleEntitlementUpdate) =>
    request<TenderModuleAccess>(OpenAPI, {
      method: 'PUT', url: accessUrl, path: { tenant_id: tenantId }, headers, body, mediaType: 'application/json',
    }),
};
