import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/api';
import LeadQualifyModal from '../src/components/leads/LeadQualifyModal.vue';

const wrappers: VueWrapper[] = [];
const lead = {
  id: 55,
  status: 'new_lead',
  is_new: true,
  customer_id: null,
  customer_name: 'Иван',
  phone: '+375291234567',
  customer_type: 'individual',
  created_at: '2026-09-27T00:00:00Z',
  attachment_count: 0,
};
const candidate = {
  id: 42,
  name: 'Иван Петров',
  phone: '+375291234567',
  type: 'individual',
  inn: null,
  full_legal_name: null,
  email: null,
};

beforeEach(() => {
  vi.spyOn(api, 'getManagerOrderScenarios').mockResolvedValue({
    items: [{ label: 'Обслуживание', workflow_type: 'maintenance', service_type: 'maintenance', hint: '' }],
  });
  vi.spyOn(api, 'getManagerCustomers').mockResolvedValue({
    items: [candidate],
    meta: { page: 1, limit: 10, total: 1, pages: 1 },
  } as never);
  vi.spyOn(api, 'getManagerCustomerBranches').mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, 'patchManagerOrder').mockResolvedValue({ id: lead.id } as never);
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
});

describe('LeadQualifyModal customer choice', () => {
  it('shows a fuzzy search result as a candidate and links only after explicit selection', async () => {
    const wrapper = mount(LeadQualifyModal, { props: { lead: lead as never } });
    wrappers.push(wrapper);
    await flushPromises();

    expect(wrapper.text()).toContain('Возможные клиенты');
    expect(wrapper.text()).toContain('Иван Петров');
    await wrapper.findAll('button').find((button) => button.text() === 'Обслуживание')!.trigger('click');
    await wrapper.findAll('button').find((button) => button.text().includes('В переговоры'))!.trigger('click');
    await flushPromises();
    expect(api.patchManagerOrder).toHaveBeenCalledWith(55, expect.not.objectContaining({ customer_id: 42 }));

    vi.mocked(api.patchManagerOrder).mockClear();
    await wrapper.findAll('button').find((button) => button.text().includes('Иван Петров'))!.trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text().includes('В переговоры'))!.trigger('click');
    await flushPromises();
    expect(api.patchManagerOrder).toHaveBeenCalledWith(55, expect.objectContaining({ customer_id: 42 }));
  });
});
