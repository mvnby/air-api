import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listEmailOriginals: vi.fn(),
  list: vi.fn(),
  reviewEmailOriginal: vi.fn(),
  downloadEmailOriginal: vi.fn(),
  reviewEmailContract: vi.fn(),
  getEmailContractReviewJob: vi.fn(),
}));

vi.mock('../src/components/service-attachments/api', () => ({ serviceAttachmentsApi: mocks }));

import EmailContractReviewLauncher from '../src/components/leads/EmailContractReviewLauncher.vue';

describe('Email original contract review', () => {
  afterEach(() => vi.clearAllMocks());

  it('starts review from the lead card and shows verified questions', async () => {
    mocks.list.mockResolvedValue({ items: [] });
    mocks.listEmailOriginals.mockResolvedValue({ items: [{
      position: 0, filename: 'Договор Кондиционеры.doc', size_bytes: 72704,
      content_type: 'application/msword',
    }] });
    const report = {
      attachment_id: 0, filename: 'Договор Кондиционеры.doc', content_sha256: 'digest',
      model: 'deepseek-v4-pro', pages: null,
      note: 'Проверьте оригинал',
      risks: [{ topic: 'Оплата', clause: '4.5', page: null,
        quote: 'Обязательства по оплате считаются исполненными',
        concern: 'Срок поступления денег не определён',
        proposal: 'Согласовать оплату по зачислению?' }],
    };
    mocks.reviewEmailOriginal.mockResolvedValue({ job_id: 'job-1', status: 'completed', report, error: null });
    const wrapper = mount(EmailContractReviewLauncher, { props: { orderId: 456 } });

    expect(mocks.listEmailOriginals).not.toHaveBeenCalled();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(mocks.listEmailOriginals).toHaveBeenCalledWith(456);
    expect(wrapper.text()).toContain('текст договора будет передан DeepSeek');
    expect(mocks.reviewEmailOriginal).toHaveBeenCalledWith(456, 0);
    expect(wrapper.text()).toContain('4.5');
    expect(wrapper.text()).toContain('Согласовать оплату по зачислению?');
    wrapper.unmount();
  });
});
