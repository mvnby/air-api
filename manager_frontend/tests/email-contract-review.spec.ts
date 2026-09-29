import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listEmailOriginals: vi.fn(),
  reviewEmailOriginal: vi.fn(),
  downloadEmailOriginal: vi.fn(),
  reviewEmailContract: vi.fn(),
  getEmailContractReviewJob: vi.fn(),
}));

vi.mock('../src/components/service-attachments/api', () => ({ serviceAttachmentsApi: mocks }));

import EmailOriginals from '../src/components/leads/EmailOriginals.vue';

describe('Email original contract review', () => {
  afterEach(() => vi.clearAllMocks());

  it('loads the historical original only on request and shows verified questions', async () => {
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
    const wrapper = mount(EmailOriginals, { props: { orderId: 456 } });

    expect(mocks.listEmailOriginals).not.toHaveBeenCalled();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Договор Кондиционеры.doc');
    expect(wrapper.text()).toContain('текст оригинала будет передан DeepSeek');
    expect(mocks.reviewEmailOriginal).not.toHaveBeenCalled();
    await wrapper.findAll('button').find((button) => button.text().includes('Проверить договор'))!.trigger('click');
    await flushPromises();
    expect(mocks.reviewEmailOriginal).toHaveBeenCalledWith(456, 0);
    expect(wrapper.text()).toContain('4.5');
    expect(wrapper.text()).toContain('Согласовать оплату по зачислению?');
    wrapper.unmount();
  });
});
