import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CancelablePromise, ManagerOrdersService, type ManagerTenderEvidenceJob } from '../src/client';
import TenderOriginalEvidencePanel from '../src/components/leads/TenderOriginalEvidencePanel.vue';

const files = ['pdf', 'docx'];
const reading: ManagerTenderEvidenceJob = { job_id: 'j', status: 'reading', processed: 1, total: 2 };
const completed: ManagerTenderEvidenceJob = {
  ...reading,
  status: 'completed',
  processed: 2,
  report: {
    documents: [
      { document_id: 'pdf', filename: 'Смета.pdf', status: 'partial', origin: 'source', diagnostics: ['Страница 4: низкая уверенность OCR.'] },
      { document_id: 'docx', filename: 'Запрос.docx', status: 'complete', origin: 'source' },
    ],
    unselected_count: 0,
    document_coverage_complete: false,
    analysis_status: 'completed',
    findings: [{
      kind: 'work_scope', value: 'Перенос сплит-системы', confidence: 'high',
      evidence: {
        document_id: 'docx', filename: 'Запрос.docx', location: 'фрагмент 8',
        quote: 'Демонтаж существующей сплит-системы с повторным монтажом.', start: 0, end: 56,
      },
    }],
  },
};

function result(value: ManagerTenderEvidenceJob) {
  return new CancelablePromise<ManagerTenderEvidenceJob>((resolve) => resolve(value));
}

describe('TenderOriginalEvidencePanel', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('shows progress, the unread page, evidence and original download', async () => {
    vi.useFakeTimers();
    const start = vi.spyOn(ManagerOrdersService, 'startManagerOrderSourceEvidenceJob').mockReturnValue(result(reading));
    const poll = vi.spyOn(ManagerOrdersService, 'getManagerOrderSourceEvidenceJob').mockReturnValue(result(completed));
    const wrapper = mount(TenderOriginalEvidencePanel, {
      props: { orderId: 699, documentIds: files, disabled: false, downloading: false },
    });
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(start).toHaveBeenCalledExactlyOnceWith(699, { document_ids: files });
    expect(wrapper.get('[role="status"]').text()).toMatch(/1 из 2/);
    await vi.advanceTimersByTimeAsync(2_500);
    await flushPromises();
    expect(poll).toHaveBeenCalledExactlyOnceWith(699, 'j');
    expect(wrapper.text()).toContain('Чтение оригиналов неполное');
    expect(wrapper.text()).toContain('Страница 4: низкая уверенность OCR.');
    expect(wrapper.get('blockquote').text()).toContain('Демонтаж существующей сплит-системы');
    expect(wrapper.text()).toContain('Запрос.docx · фрагмент 8');
    await wrapper.findAll('button').find((button) => button.text() === 'Запрос.docx')!.trigger('click');
    expect(wrapper.emitted('download')).toEqual([['docx']]);
    wrapper.unmount();
  });

  it('clears the old job and cancels the request when the selection changes', async () => {
    const request = new CancelablePromise<ManagerTenderEvidenceJob>(() => {});
    vi.spyOn(ManagerOrdersService, 'startManagerOrderSourceEvidenceJob').mockReturnValue(request);
    const wrapper = mount(TenderOriginalEvidencePanel, {
      props: { orderId: 699, documentIds: files, disabled: false, downloading: false },
    });
    await wrapper.get('button').trigger('click');
    expect(wrapper.get('[role="status"]').exists()).toBe(true);
    await wrapper.setProps({ documentIds: ['docx'] });
    expect(request.isCancelled).toBe(true);
    expect(wrapper.find('[role="status"]').exists()).toBe(false);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
