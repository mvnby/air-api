import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService, type NativeTemplateVersionItem } from '../src/client';
import TemplateAuditPanel from '../src/features/documents/settings/TemplateAuditPanel.vue';
import { templateAuditApi, type AuditContext, type TemplateAuditReport } from '../src/features/documents/integrations/template-audit-api';

const wrappers: VueWrapper[] = [];
const hash = 'a'.repeat(64);
const candidateHash = 'b'.repeat(64);
const originalUrl = globalThis.URL;
const fixture = (): TemplateAuditReport => ({
  id: 7, template_id: 10, version_id: 20, template_name: 'Договор с монтажом', version_number: 3, legal_entity_id: 5, customer_id: null, revision: 2,
  source_hash: hash, context_hash: hash, legal_sources_hash: hash, checked_at: '2026-11-10T10:00:00Z',
  coverage: { complete: true, reasons: [] }, checklist: { tax: 'unverified' }, stale: false, stale_reasons: [],
  legal_currency: 'requires_external_recheck', manager_url: '/manager/settings/documents?legalEntityId=5&auditReportId=7',
  findings: [{
    id: 'finding-1', block_id: 'paragraph-1', location_label: 'Основной текст', original_text: 'Старая формулировка', proposed_text: 'Новая формулировка',
    category: 'tax', risk: 'Налоговый риск', severity: 'high', confidence: 'medium', verification: 'unverified',
    applicability: 'Для организаций', status: 'proposal', decision_history: [],
    occurrences: [
      { block_id: 'paragraph-1', text: 'Старая формулировка — основной текст', part: 'word/document.xml', location: '/p[1]' },
      { block_id: 'footer-1', text: 'Старая формулировка — нижний колонтитул', part: 'word/footer1.xml', location: '/p[1]' },
    ],
    sources: [{ url: 'https://pravo.by/example', title: 'Налоговый кодекс', provision: 'Статья 1', excerpt: 'Текст нормы',
      checked_at: '2026-11-10T10:00:00Z', effective_from: '2026-01-01', edition: '2026', applicability: 'Организации',
      content_hash: hash, official: true, verification: 'unverified' }],
  }],
  proposals: [{ id: 1, base_version_id: 20, version_id: 21, version_number: 4, status: 'draft', source_hash: candidateHash,
    created_by: 1, channel: 'mcp', created_at: '2026-11-10T10:01:00Z', edits: [
      { finding_id: 'finding-1', block_id: 'paragraph-1', expected_text: 'Старая формулировка', replacement_text: 'Новая формулировка', reason: 'Уточнена налоговая оговорка' },
    ] }],
});
const contextFixture = (): AuditContext => ({
  synthetic: true, label: 'Вымышленный клиент', source_hash: candidateHash, context_hash: hash, legal_sources_hash: hash,
  values: { 'customer.name': 'Учебный клиент', 'customer.unp': '000000000' },
  conditions: { 'customer.is_individual': true, 'customer.is_organization': false, 'customer.is_individual_entrepreneur': false,
    'seller.is_vat_payer': false, 'seller.is_not_vat_payer': true, 'contract.extra_condition': false }, table_rows: {},
  field_labels: { 'customer.name': 'Имя клиента', 'customer.unp': 'УНП клиента' },
  condition_labels: { 'customer.is_individual': 'Клиент — физлицо', 'customer.is_organization': 'Клиент — организация', 'customer.is_individual_entrepreneur': 'Клиент — ИП', 'seller.is_vat_payer': 'Продавец платит НДС', 'seller.is_not_vat_payer': 'Продавец не платит НДС', 'contract.extra_condition': 'Дополнительные работы' },
  table_labels: {}, row_field_labels: {},
});
const version = (id: number, status: string): NativeTemplateVersionItem => ({
  id, template_id: 10, version: id - 19, status, renderer: 'native', checksum_sha256: id === 20 ? hash : candidateHash,
  placeholder_schema: {}, created_at: '2026-11-10T10:00:00Z',
});
const open = async () => {
  const wrapper = mount(TemplateAuditPanel, { props: { legalEntityId: 5 } });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find((item) => item.text() === text)!;
const preparePdf = async (wrapper: VueWrapper) => {
  await button(wrapper, 'Подготовить учебный пример').trigger('click');
  await flushPromises();
  await wrapper.get('[data-testid="audit-preview-pdf"]').trigger('click');
  await flushPromises();
};

beforeEach(() => {
  window.history.replaceState({}, '', '/manager/settings/documents');
  vi.stubGlobal('URL', class extends originalUrl {
    static createObjectURL = vi.fn(() => 'blob:audit-pdf');
    static revokeObjectURL = vi.fn();
  });
  vi.spyOn(templateAuditApi, 'list').mockResolvedValue({ items: [fixture()], total: 1, page: 1, limit: 25 });
  vi.spyOn(templateAuditApi, 'get').mockResolvedValue(fixture());
  vi.spyOn(templateAuditApi, 'decide').mockResolvedValue({ ...fixture(), revision: 3 });
  vi.spyOn(templateAuditApi, 'context').mockResolvedValue(contextFixture());
  vi.spyOn(templateAuditApi, 'preview').mockResolvedValue(new Blob(['%PDF-example'], { type: 'application/pdf' }));
  vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeTemplateVersions').mockResolvedValue({ items: [version(20, 'active'), version(21, 'draft')] });
  vi.spyOn(ManagerDocumentSystemService, 'activateManagerNativeTemplateVersion').mockResolvedValue(version(21, 'active'));
});
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

describe('TemplateAuditPanel', () => {
  it('shows source/proposed text, repeated contexts and unverified law separately from complete extraction', async () => {
    const wrapper = await open();
    expect(templateAuditApi.list).toHaveBeenCalledWith(5, 1);
    expect(wrapper.get('[data-testid="audit-coverage"]').text()).toContain('Весь текст DOCX');
    expect(wrapper.get('[data-testid="audit-coverage"]').text()).toContain('не подтверждает соответствие законодательству');
    expect(wrapper.text()).toContain('Юридически не проверено');
    expect(wrapper.text()).toContain('Старая формулировка — нижний колонтитул');
    expect(wrapper.text()).toContain('Налоговый кодекс');
    expect(wrapper.text()).toContain('Официальный источник · не проверен');
    expect(wrapper.get('[data-testid="audit-report-select"]').text()).toContain('Договор с монтажом · версия 3 · проверка');
    expect(wrapper.get('[data-testid="audit-report-select"]').text()).not.toContain('шаблон №10');
    expect(wrapper.text()).toContain('Нижний колонтитул · абзац 1');
    for (const details of wrapper.findAll('details').filter((item) => item.get('summary').text() === 'Технические сведения')) {
      expect(details.attributes('open')).toBeUndefined();
    }
    expect(wrapper.get('[data-testid="audit-activate"]').attributes('disabled')).toBeDefined();
    expect(ManagerDocumentSystemService.activateManagerNativeTemplateVersion).not.toHaveBeenCalled();
  });

  it('opens a report from the full link even when it is outside the first page', async () => {
    window.history.replaceState({}, '', '/manager/settings/documents?legalEntityId=5&auditReportId=99');
    vi.mocked(templateAuditApi.get).mockResolvedValue({ ...fixture(), id: 99 });
    const wrapper = await open();
    expect(templateAuditApi.get).toHaveBeenCalledWith(99);
    expect(wrapper.get<HTMLSelectElement>('[data-testid="audit-report-select"]').element.value).toBe('99');
    await wrapper.setProps({ legalEntityId: 6 });
    await flushPromises();
    expect(templateAuditApi.get).toHaveBeenLastCalledWith(7);
  });

  it('saves a reason and observed revision/hashes, then uses the returned revision', async () => {
    const wrapper = await open();
    await wrapper.get('[aria-label="Решение по замечанию 1"]').setValue('needs_legal_review');
    await wrapper.get('[aria-label="Основание решения 1"]').setValue('Проверить применимость к ИП');
    await wrapper.get('[data-testid="audit-finding-finding-1"] form').trigger('submit');
    await flushPromises();
    expect(templateAuditApi.decide).toHaveBeenCalledWith(7, 'finding-1', {
      expected_revision: 2, source_hash: hash, context_hash: hash, legal_sources_hash: hash,
      status: 'needs_legal_review', reason: 'Проверить применимость к ИП',
    });
    expect(wrapper.get('[data-testid="audit-report-technical"]').text()).toContain('"revision": 3');
  });

  it('blocks stale report decisions, preview and activation while preserving review text', async () => {
    vi.mocked(templateAuditApi.get).mockResolvedValue({ ...fixture(), stale: true, stale_reasons: ['source_changed'] });
    const wrapper = await open();
    expect(wrapper.get('[data-testid="audit-stale"]').text()).toContain('Изменился исходный DOCX');
    expect(wrapper.get('[aria-label="Решение по замечанию 1"]').attributes('disabled')).toBeDefined();
    expect(button(wrapper, 'Подготовить учебный пример').attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('Новая формулировка');
  });

  it('marks an older decision without resetting its status or history after wording or evidence changes', async () => {
    const value = fixture();
    Object.assign(value.findings[0]!, {
      status: 'accepted', decision_current: false,
      decision_history: [{ from: 'proposal', to: 'accepted', reason: 'Предыдущее обоснование', at: '2026-11-10T10:02:00Z', actor: 1 }],
    });
    vi.mocked(templateAuditApi.get).mockResolvedValue(value);
    const wrapper = await open();
    const finding = wrapper.get('[data-testid="audit-finding-finding-1"]');
    expect(finding.get('[role="status"]').text()).toBe('Решение относится к прежней редакции или источникам. Проверьте и сохраните решение заново.');
    expect(wrapper.get<HTMLSelectElement>('[aria-label="Решение по замечанию 1"]').element.value).toBe('accepted');
    expect(finding.text()).toContain('Предыдущее обоснование');
    expect(templateAuditApi.decide).not.toHaveBeenCalled();
  });

  it('uses editable fictional context for the inactive candidate and requires separate activation', async () => {
    const wrapper = await open();
    await button(wrapper, 'Подготовить учебный пример').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="audit-customer-type"]').setValue('individual_entrepreneur');
    expect(wrapper.get('[data-testid="audit-preview-scenario"]').text()).toBe('ИП, без НДС — вымышленные данные');
    await wrapper.get('[data-testid="audit-vat"]').setValue(true);
    expect(wrapper.get('[data-testid="audit-preview-scenario"]').text()).toBe('ИП, с НДС — вымышленные данные');
    await wrapper.get('[aria-label="Имя клиента"]').setValue('Учебный ИП');
    await wrapper.get('[aria-label="Очистить: УНП клиента"]').trigger('click');
    await wrapper.get('[data-testid="audit-preview-pdf"]').trigger('click');
    await flushPromises();
    expect(templateAuditApi.preview).toHaveBeenCalledWith(7, 1, expect.objectContaining({
      synthetic: true, source_hash: candidateHash, context_hash: hash, legal_sources_hash: hash, format: 'pdf',
      label: 'ИП, с НДС — вымышленные данные',
      values: { 'customer.name': 'Учебный ИП', 'customer.unp': '' },
      conditions: expect.objectContaining({ 'customer.is_individual_entrepreneur': true, 'customer.is_individual': false }),
    }));
    expect(Object.keys(vi.mocked(templateAuditApi.preview).mock.calls[0]![2].conditions).sort()).toEqual(Object.keys(contextFixture().conditions).sort());
    expect(wrapper.get('iframe').attributes('src')).toBe('blob:audit-pdf');
    expect(wrapper.get('[data-testid="audit-activate"]').attributes('disabled')).toBeUndefined();
    expect(ManagerDocumentSystemService.activateManagerNativeTemplateVersion).not.toHaveBeenCalled();
    await wrapper.get('[data-testid="audit-activate"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.activateManagerNativeTemplateVersion).toHaveBeenCalledWith(10, 21, 5, 20);
    expect(wrapper.emitted('activated')).toHaveLength(1);
  });

  it('invalidates changed examples and refuses a concurrently changed active version', async () => {
    const wrapper = await open();
    await preparePdf(wrapper);
    await wrapper.get('[aria-label="Имя клиента"]').setValue('Другой учебный пример');
    expect(wrapper.find('iframe').exists()).toBe(false);
    expect(wrapper.get('[data-testid="audit-activate"]').attributes('disabled')).toBeDefined();
    await wrapper.get('[data-testid="audit-preview-pdf"]').trigger('click');
    await flushPromises();
    vi.mocked(templateAuditApi.get).mockResolvedValue({ ...fixture(), stale: true, stale_reasons: ['issuer_template_or_customer_context_changed'] });
    await wrapper.get('[data-testid="audit-activate"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.activateManagerNativeTemplateVersion).not.toHaveBeenCalled();
    expect(wrapper.get('[role="alert"]').text()).toContain('Отчёт изменился');
  });

  it('can activate a proposal made from an explicit inactive base using the currently active version guard', async () => {
    const wrapper = await open();
    await preparePdf(wrapper);
    vi.mocked(ManagerDocumentSystemService.listManagerNativeTemplateVersions).mockResolvedValue({ items: [version(20, 'draft'), version(22, 'active'), version(21, 'draft')] });
    await wrapper.get('[data-testid="audit-activate"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.activateManagerNativeTemplateVersion).toHaveBeenCalledWith(10, 21, 5, 22);
  });

  it('blocks a stale proposal and explains mandatory visual review separately from text coverage', async () => {
    const value = fixture();
    value.coverage.requires_visual_review = true;
    value.proposals[0]!.stale = true;
    vi.mocked(templateAuditApi.get).mockResolvedValue(value);
    const wrapper = await open();
    expect(wrapper.text()).toContain('изображения или другие нетекстовые элементы');
    expect(wrapper.text()).toContain('Предлагаемая версия устарела');
    expect(button(wrapper, 'Подготовить учебный пример').attributes('disabled')).toBeDefined();
  });

  it('edits labelled fields, conditions and table rows without JSON and can restore an empty requisite', async () => {
    const sample = contextFixture();
    sample.table_rows = { goods: [{ 'line.name': 'Учебное оборудование', 'line.price': '100.00' }] };
    sample.table_labels = { goods: 'Оборудование' };
    sample.row_field_labels = { 'line.name': 'Наименование', 'line.price': 'Цена' };
    vi.mocked(templateAuditApi.context).mockResolvedValue(sample);
    const wrapper = await open();
    await button(wrapper, 'Подготовить учебный пример').trigger('click');
    await flushPromises();
    await wrapper.get('[aria-label="Очистить: УНП клиента"]').trigger('click');
    expect(wrapper.get<HTMLTextAreaElement>('[aria-label="УНП клиента"]').element.value).toBe('');
    await wrapper.get('[aria-label="Вернуть пример: УНП клиента"]').trigger('click');
    expect(wrapper.get<HTMLTextAreaElement>('[aria-label="УНП клиента"]').element.value).toBe('000000000');
    await wrapper.get('[aria-label="Дополнительные работы"]').setValue(true);
    await wrapper.get('[aria-label="Цена, строка 1: Оборудование"]').setValue('125.00');
    await button(wrapper, 'Добавить строку').trigger('click');
    await wrapper.get('[aria-label="Наименование, строка 2: Оборудование"]').setValue('Дополнительная работа');
    await wrapper.get('[data-testid="audit-preview-pdf"]').trigger('click');
    await flushPromises();
    expect(templateAuditApi.preview).toHaveBeenCalledWith(7, 1, expect.objectContaining({
      conditions: expect.objectContaining({ 'contract.extra_condition': true }),
      table_rows: { goods: [
        { 'line.name': 'Учебное оборудование', 'line.price': '125.00' },
        { 'line.name': 'Дополнительная работа', 'line.price': '100.00' },
      ] },
    }));
    expect(wrapper.find('[data-testid="audit-context-values"]').exists()).toBe(false);
  });

  it('explains Word field coverage limits and keeps raw diagnostic paths in closed technical details', async () => {
    vi.mocked(templateAuditApi.get).mockResolvedValue({ ...fixture(), coverage: {
      complete: false, reasons: [{ code: 'field_instruction', part: 'word/footer1.xml', location: '/w:ftr/w:p[1]/w:fldSimple' }],
    } });
    const wrapper = await open();
    expect(wrapper.text()).toContain('номера страниц PAGE и NUMPAGES');
    expect(wrapper.text()).toContain('Адресная правка отключена');
    expect(button(wrapper, 'Подготовить учебный пример').attributes('disabled')).toBeDefined();
    expect(wrapper.get('[data-testid="audit-report-technical"]').attributes('open')).toBeUndefined();
  });

  it('loads bounded occurrence pages without discarding an unsaved decision reason', async () => {
    const first = fixture();
    Object.assign(first.findings[0]!, { occurrences_total: 101, occurrences_page: 1, occurrences_next_page: 2 });
    vi.mocked(templateAuditApi.get).mockResolvedValueOnce(first);
    const wrapper = await open();
    await wrapper.get('[aria-label="Основание решения 1"]').setValue('Сохранить мой комментарий');
    const next = fixture();
    Object.assign(next.findings[0]!, { occurrences: [{ block_id: 'end-1', text: 'Совпадение на следующей странице', part: 'word/document.xml', location: '/p[102]' }], occurrences_total: 101, occurrences_page: 2, occurrences_next_page: null });
    vi.mocked(templateAuditApi.get).mockResolvedValueOnce(next);
    await button(wrapper, 'Следующие вхождения').trigger('click');
    await flushPromises();
    expect(templateAuditApi.get).toHaveBeenLastCalledWith(7, { findingId: 'finding-1', page: 2 });
    expect(wrapper.text()).toContain('Совпадение на следующей странице');
    expect(wrapper.get<HTMLInputElement>('[aria-label="Основание решения 1"]').element.value).toBe('Сохранить мой комментарий');
    expect(button(wrapper, 'Предыдущие вхождения')).toBeDefined();
    expect(wrapper.text()).not.toContain('Все вхождения');
  });

  it('discards an in-flight report when the selected issuer changes', async () => {
    let resolveReport!: (value: TemplateAuditReport) => void;
    vi.mocked(templateAuditApi.get).mockImplementationOnce(() => new Promise((resolve) => { resolveReport = resolve; }) as ReturnType<typeof templateAuditApi.get>);
    const wrapper = mount(TemplateAuditPanel, { props: { legalEntityId: 5 } });
    wrappers.push(wrapper);
    await flushPromises();
    await wrapper.setProps({ legalEntityId: null });
    resolveReport(fixture());
    await flushPromises();
    expect(wrapper.find('[data-testid="template-audit-panel"]').exists()).toBe(false);
  });
});
