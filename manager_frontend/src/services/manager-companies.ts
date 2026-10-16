import { OpenAPI, type ManagerAccountCompany, type ManagerAccountCompaniesResponse, type CompanySiteResponse, type PlatformCompanyResponse, type PlatformCompanyUpdate } from '../client';
import { request } from '../client/core/request';

export type CompanyChoice = ManagerAccountCompany;
export type CompanyChoices = ManagerAccountCompaniesResponse;
export type CompanySite = CompanySiteResponse;
export type PlatformCompany = PlatformCompanyResponse;
export const managerCompaniesApi = {
  choices: (page = 1) => request<CompanyChoices>(OpenAPI, { method: 'GET', url: '/api/manager/account/companies', query: { page, limit: 100 } }),
  sites: async (): Promise<{ items: CompanySite[] }> => {
    const first = await request<{ items: CompanySite[]; total: number; page: number; limit: number }>(OpenAPI, { method: 'GET', url: '/api/manager/company/sites', query: { page: 1, limit: 100 } });
    const items = [...first.items];
    for (let page = 2; items.length < first.total; page++) {
      const next = await request<typeof first>(OpenAPI, { method: 'GET', url: '/api/manager/company/sites', query: { page, limit: 100 } });
      if (!next.items.length) break;
      items.push(...next.items);
    }
    return { items };
  },
  list: (page: number, search?: string) => request<{ items: PlatformCompany[]; total: number; page: number; limit: number }>(OpenAPI, { method: 'GET', url: '/api/manager/platform/companies', query: { page, limit: 50, search } }),
  update: (company: PlatformCompany, changes: Omit<PlatformCompanyUpdate, 'expected_updated_at'>) => request<PlatformCompany>(OpenAPI, {
    method: 'PATCH', url: `/api/manager/platform/companies/${company.id}`, headers: { 'X-Kitlane-Team': '1' },
    body: { ...changes, expected_updated_at: company.updated_at }, mediaType: 'application/json',
  }),
};
