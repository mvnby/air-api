import { beforeEach, describe, expect, it, vi } from 'vitest';
const requestMock = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock('../src/client/core/request', () => ({ request: requestMock }));
import { orderResponsibilityApi } from '../src/services/order-responsibility';
import { api } from '../src/api';
beforeEach(() => requestMock.mockClear());
describe('order responsibility HTTP contract', () => {
  it('sends version and team protection in their correct locations, including clearing', async () => {
    await orderResponsibilityApi.assign(11, 7, 3); await orderResponsibilityApi.assign(11, null, 4); await orderResponsibilityApi.candidates(2);
    expect(requestMock.mock.calls.map(call => call[1])).toEqual([
      expect.objectContaining({ method: 'PATCH', url: '/api/manager/orders/11/responsible', headers: { 'X-Kitlane-Team': '1' }, body: { responsible_staff_user_id: 7, expected_version: 3 } }),
      expect.objectContaining({ method: 'PATCH', headers: { 'X-Kitlane-Team': '1' }, body: { responsible_staff_user_id: null, expected_version: 4 } }),
      expect.objectContaining({ method: 'GET', url: '/api/manager/order-responsibles', query: { page: 2, limit: 100 } }),
    ]); expect(requestMock.mock.calls[0]![1].query).toBeUndefined();
  });
  it('passes Mine to server pagination without discarding the other business filters', async () => {
    await api.getManagerOrders({ segment: 'b2b', assignedToMe: true, customerId: 12, status: 'execution', search: 'офис', sort: 'margin_desc', page: 2, limit: 100 });
    expect(requestMock.mock.calls[0]![1].query).toEqual({ segment: 'b2b', assigned_to_me: true, customer_id: 12, status: 'execution', search: 'офис', sort: 'margin_desc', page: 2, limit: 100, overdue_only: false });
  });
});
