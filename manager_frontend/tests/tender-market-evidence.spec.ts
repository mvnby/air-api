import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManagerTenderModuleService } from '../src/client';
import TenderMarketEvidencePanel from '../src/features/tenders/TenderMarketEvidencePanel.vue';

describe('Tender market evidence', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens the saved public report with a literal quote and its source', async () => {
    const sourceUrl = 'https://goszakupki.by/single-source/view/3876716';
    vi.spyOn(ManagerTenderModuleService, 'getManagerTenderMarketEvidence').mockResolvedValue({
      status: 'completed', checked_at: '2026-11-26T00:00:00Z', documents_source_url: sourceUrl,
      report: {
        document_coverage_complete: false, unselected_count: 0, analysis_status: 'completed',
        documents: [{ document_id: 'a', filename: 'ТЗ.docx', origin: 'source', status: 'complete' }],
        findings: [{
          kind: 'work_scope', value: 'Перенести кондиционер', confidence: 'high',
          evidence: { document_id: 'a', filename: 'ТЗ.docx', location: 'Фрагмент 4', quote: 'Демонтировать сплит-систему.',
            start: 0, end: 28 },
        }],
      },
    });
    const request = vi.spyOn(ManagerTenderModuleService, 'requestManagerTenderMarketEvidence');
    const page = mount(TenderMarketEvidencePanel, { props: { publicationId: 699 } });
    await flushPromises();
    expect(page.get('blockquote').text()).toBe('Демонтировать сплит-систему.');
    expect(page.text()).toContain('Чтение оригиналов неполное');
    expect(page.get('a').attributes('href')).toBe(sourceUrl);
    expect(request).not.toHaveBeenCalled();
    page.unmount();
  });
});
