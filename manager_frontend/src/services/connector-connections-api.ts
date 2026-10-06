import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';

export type ConnectorGrant = {
  id: number;
  client_id: string;
  tenant_id: number;
  storefront_id: number;
  scopes: string[];
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
};

type GrantList = { items: ConnectorGrant[]; csrf_token: string };
const url = '/api/manager/connector/grants';

export const connectorConnectionsApi = {
  list: () => request<GrantList>(OpenAPI, { method: 'GET', url }),
  revoke: async (id: number): Promise<void> => {
    // Obtain a fresh session-bound nonce even when the profile stayed open for hours.
    const { csrf_token } = await connectorConnectionsApi.list();
    await request<void>(OpenAPI, {
      method: 'POST', url: `${url}/${id}/revoke`, headers: { 'X-CSRF-Token': csrf_token },
    });
  },
};
