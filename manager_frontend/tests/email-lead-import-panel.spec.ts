import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  importManagerEmailLeads: vi.fn(),
  getManagerEmailLeadImportStatus: vi.fn(),
}));

vi.mock('../src/client', () => ({
  ManagerMailService: {
    importManagerEmailLeads: mocks.importManagerEmailLeads,
    getManagerEmailLeadImportStatus: mocks.getManagerEmailLeadImportStatus,
  },
}));

import EmailLeadImportPanel from '../src/components/leads/EmailLeadImportPanel.vue';

describe('EmailLeadImportPanel', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('reports created incoming requests and keeps review details available', async () => {
    mocks.importManagerEmailLeads.mockResolvedValue({
      status: 'completed',
      result: { processed: 3, created: 2, duplicates: 1, candidates: 2, decisions: [{ status: 'created', sender_email: 'anna@example.test', subject: 'Монтаж' }] },
    });
    const wrapper = mount(EmailLeadImportPanel);
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('imported')).toEqual([[2]]);
    expect(wrapper.text()).toContain('Результаты проверки');
    expect(wrapper.get('details').attributes('open')).toBeUndefined();
    wrapper.unmount();
  });

  it('does not poll after it is unmounted', async () => {
    vi.useFakeTimers();
    mocks.importManagerEmailLeads.mockResolvedValue({ status: 'running' });
    const wrapper = mount(EmailLeadImportPanel);
    await wrapper.get('button').trigger('click');
    await flushPromises();
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(3000);
    expect(mocks.getManagerEmailLeadImportStatus).not.toHaveBeenCalled();
  });

  it('shows a failed import as an error instead of a completed check', async () => {
    mocks.importManagerEmailLeads.mockResolvedValue({ status: 'failed', error: 'Почтовый сервер недоступен' });
    const wrapper = mount(EmailLeadImportPanel);
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Почтовый сервер недоступен');
    expect(wrapper.emitted('imported')).toBeUndefined();
    wrapper.unmount();
  });
});
