import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ManagerDocumentSystemService,
  ManagerDocsService,
  ManagerEquipmentLinksService,
  ManagerContractsService,
  ManagerEquipmentLinksService,
  ManagerService,
  CancelablePromise,
  OpenAPI,
  type ManagedDocumentItem,
  type ManagerOrderDetailResponse,
} from '../src/client';
import NativeDocumentsWorkspace from '../src/features/documents/components/NativeDocumentsWorkspace.vue';
import DocumentVersionHistory from '../src/features/documents/components/DocumentVersionHistory.vue';
import { groupDocumentVersions } from '../src/features/documents/model/document-version-history';
import { googleDocumentEditorApi } from '../src/features/documents/integrations/google-document-editor-api';
import { managerSession } from '../src/services/manager-session';

const confirmDialog = vi.hoisted(() => vi.fn().mockResolvedValue(true));
const openNativeDocumentPreview = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog }));
vi.mock('../src/features/documents/integrations/native-document-preview', () => ({ openNativeDocumentPreview }));

const NOW = '2026-08-27T00:00:00Z';
const baseOrder = {
  id: 42,
  status: 'negotiation',
  created_at: NOW,
  total_amount: 3_200,
  total_cost: 2_000,
  margin: 1_200,
  is_paid: false,
  customer: {
    id: 11,
    type: 'company',
    name: 'ООО Климат',
    inn: '123456789',
  },
  customer_contract_id: 91,
  customer_contract: {
    id: 91,
    customer_id: 11,
    number: '44-ЭА/2026',
    valid_from: '2020-08-01',
    valid_until: '2099-07-31',
    document_role_type: 'executor_customer',
    status: 'active',
  },
  documents: [],
  proposals: [{
    id: 7,
    order_id: 42,
    name: 'Основное',
    status: 'accepted',
    is_selected: true,
    is_archived: false,
    sort_order: 0,
    created_at: NOW,
    service_lines: [{ id: 45, proposal_id: 7, service_title: 'Диагностика', quantity: 3, price: 100, line_total: 300 }],
  }],
  product_lines: [],
  service_lines: [],
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const wrappers: VueWrapper[] = [];
const revision = (id: number, status: string, replaces_document_id: number | null = null, doc_type = 'contract'): ManagedDocumentItem => ({
  id, order_id: 42, legal_entity_id: 5, doc_type, status, provider: 'native',
  official_full_number: `Д-2026-${id}`, display_number: `Д-2026-${id}`,
  date: NOW, created_at: NOW, replaces_document_id, artifacts: [],
});
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

beforeEach(() => {
  confirmDialog.mockReset().mockResolvedValue(true);
  openNativeDocumentPreview.mockReset().mockResolvedValue(undefined);
  vi.spyOn(ManagerContractsService, 'getManagerCustomerContracts').mockResolvedValue({ items: [] });
  vi.spyOn(ManagerService, 'getManagerCustomerBranches').mockResolvedValue({ items: [] });
  vi.spyOn(googleDocumentEditorApi, 'getConnectionStatus').mockResolvedValue({
    connected: false,
    provider: 'google_drive',
    account_label: null,
    managed_folder_url: null,
    connected_at: null,
    last_verified_at: null,
    last_error_code: null,
  });
  vi.spyOn(googleDocumentEditorApi, 'getSession').mockResolvedValue(null);
  vi.spyOn(googleDocumentEditorApi, 'createSession').mockResolvedValue({
    id: 'document-session-77',
    status: 'ready',
    edit_url: 'https://docs.google.com/document/d/document-77/edit',
    can_edit: true,
    base_checksum_sha256: 'a'.repeat(64),
    remote_revision: 'revision-1',
    modified_at: NOW,
    last_synced_at: NOW,
    detail: null,
  });
  vi.spyOn(googleDocumentEditorApi, 'syncSession').mockResolvedValue({
    session: {
      id: 'document-session-77',
      status: 'ready',
      edit_url: 'https://docs.google.com/document/d/document-77/edit',
      can_edit: true,
      base_checksum_sha256: 'b'.repeat(64),
      remote_revision: 'revision-2',
      modified_at: NOW,
      last_synced_at: NOW,
      detail: null,
    },
    newTemplateVersionCreated: false,
  });
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({
    items: [{
      id: 5,
      tenant_id: 1,
      slug: 'mvn',
      display_name: 'ООО МВН',
      is_vat_payer: false,
      is_default: true,
      requisites: {
        city: 'Витебск',
        default_goods_warranty_months: '48',
        default_work_warranty_months: '12',
        offer_url: 'https://mvn.by/offer',
        offer_version: '1.0',
        offer_published_on: '04.06.2026',
      },
      status: 'active',
      created_at: NOW,
      updated_at: NOW,
    }],
  });
  vi.spyOn(ManagerDocumentSystemService, 'getManagerDocumentPdfRuntime').mockResolvedValue({
    available: true,
    provider: 'gotenberg',
    detail: 'healthy',
  });
  vi.spyOn(ManagerDocumentSystemService, 'listManagerManagedOrderDocuments').mockResolvedValue({ items: [] });
  vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeDocumentTemplates').mockImplementation(
    async (_legalEntityId, documentType) => ({
      items: [{
        id: 100,
        tenant_id: 1,
        legal_entity_id: 5,
        name: `Шаблон ${documentType || ''}`,
        doc_type: documentType || 'contract',
        is_default: true,
        is_active: true,
        sort_order: 0,
        created_at: NOW,
      }],
    }),
  );
  vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeTemplateVersions').mockResolvedValue({
    items: [{
      id: 101,
      template_id: 100,
      version: 1,
      status: 'active',
      renderer: 'docx',
      checksum_sha256: 'a'.repeat(64),
      placeholder_schema: {},
      created_at: NOW,
    }],
  });
  vi.spyOn(ManagerDocumentSystemService, 'checkManagerManagedDocumentReadiness').mockResolvedValue({
    checked: true, can_issue: true, missing_fields: [], template_id: 100, template_version_id: 101,
  });
  vi.spyOn(ManagerDocumentSystemService, 'getManagerManagedDocumentReadiness').mockResolvedValue({
    checked: true, can_issue: true, missing_fields: [],
  });
  vi.spyOn(ManagerDocumentSystemService, 'createManagerManagedDocumentDraft').mockResolvedValue({} as never);
  vi.spyOn(ManagerDocumentSystemService, 'issueManagerManagedDocument').mockResolvedValue({} as never);
  vi.spyOn(ManagerDocumentSystemService, 'deleteManagerManagedDocumentDraft').mockResolvedValue(undefined as never);
  vi.spyOn(ManagerDocumentSystemService, 'getManagerConsumerEquipmentDefaults').mockResolvedValue({
    equipment_brand: 'Midea',
    equipment_model: 'MSAG-09HRN1',
    equipment_serial: null,
    goods_warranty_months: 36,
    goods_warranty_terms: 'По условиям изготовителя',
  });
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
  managerSession.auth.value = null;
});

const mountWorkspace = async (beforeGenerate?: (type: string) => unknown | Promise<unknown>, order = baseOrder) => {
  const wrapper = mount(NativeDocumentsWorkspace, { props: { order, beforeGenerate } });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};

describe('NativeDocumentsWorkspace', () => {
  it('highlights the contract from the Manager link among the saved documents', async () => {
    const previousUrl = window.location.href;
    window.history.replaceState(null, '', '/manager/orders/42?proposalId=7&section=documents&documentId=77');
    try {
      vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({
        items: [revision(76, 'draft'), revision(77, 'draft')],
      });
      const wrapper = await mountWorkspace();
      expect(wrapper.get('[data-testid="current-document-77"]').attributes('tabindex')).toBe('-1');
      expect(wrapper.get('[data-testid="current-document-76"]').attributes('tabindex')).toBeUndefined();
    } finally {
      window.history.replaceState(null, '', previousUrl);
    }
  });

  it.each(['individual', 'company'])('creates a repair act for a %s using only the confirmed conclusion', async (type) => {
    vi.mocked(ManagerDocumentSystemService.listManagerNativeDocumentTemplates).mockResolvedValue({ items: [] });
    const wrapper = await mountWorkspace(undefined, {
      ...baseOrder, workflow_type: 'repair', customer: { ...baseOrder.customer!, type },
      repair_meta: {
        equipment_model: 'A-09', equipment_serial_number: 'SN-01',
        confirmed_facts: ['Утечка в соединении'], diagnostic_notes: 'Внутренние замеры',
        repair_recommendation: 'Герметизировать соединение', repair_status: 'completed',
      },
    });
    const field = (id: string) => wrapper.get<HTMLInputElement>(`[data-testid="repair-${id}"]`);
    expect(wrapper.get('[data-testid="native-document-type-repair_defect_act"]').attributes('aria-pressed')).toBe('true');
    expect(field('equipment').element.value).toBe('A-09 S/N SN-01');
    expect(field('finding').element.value).toBe('');
    await wrapper.findAll('button').find(button => button.text() === 'Подставить результат диагностики из заказа')!.trigger('click');
    expect(field('finding').element.value).toBe('Утечка в соединении');
    expect(field('verdict').element.value).toBe('');
    expect(field('cost').element.value).toBe('');
    const create = wrapper.get('[data-testid="create-native-draft"]');
    expect(create.attributes('disabled')).toBeDefined();
    await field('verdict').setValue('repairable');
    await wrapper.findAll('button').find(button => button.text() === 'Подставить рекомендацию из заказа')!.trigger('click');
    await field('cost').setValue('240 BYN');
    await field('term').setValue('3 рабочих дня');
    await field('verdict').setValue('needs_diagnostics');
    expect(field('cost').element.value).toBe('');
    expect(field('term').element.value).toBe('');
    await field('recommendation').setValue('Уточнить место утечки');
    await create.trigger('click'); await flushPromises();
    const payload = {
      document_type: 'repair_defect_act',
      repair_defect: { equipment: 'A-09 S/N SN-01', finding: 'Утечка в соединении', recommendation: 'Уточнить место утечки',
        verdict: 'needs_diagnostics', cost: null, term: null, restriction: null },
    };
    expect(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).toHaveBeenCalledWith(42, expect.objectContaining(payload));
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42, expect.objectContaining(payload));
  });

  it('takes replacement terms from the issued act and clears them when the replacement is cancelled', async () => {
    const terms = { equipment: 'Старый блок', finding: 'Повторный выход из строя', verdict: 'uneconomical' as const,
      recommendation: 'Заменить оборудование', cost: null, term: null };
    const original = { ...revision(60, 'issued', null, 'repair_defect_act'), repair_defect: terms };
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [original] });
    const wrapper = await mountWorkspace(undefined, {
      ...baseOrder, workflow_type: 'repair', repair_meta: { equipment_model: 'Блок из текущего заказа' },
    });
    const scroll = vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 0);
    await wrapper.findAll('button').find(button => button.text() === 'Создать исправленную редакцию')!.trigger('click');
    const field = (id: string) => wrapper.get<HTMLInputElement>(`[data-testid="repair-${id}"]`);
    expect(field('equipment').element.value).toBe('Старый блок');
    expect(field('verdict').element.value).toBe('uneconomical');
    expect(field('finding').element.value).toBe('Повторный выход из строя');
    await wrapper.findAll('button').find(button => button.text() === 'Отменить')!.trigger('click');
    expect(field('equipment').element.value).toBe('Блок из текущего заказа');
    expect(field('verdict').element.value).toBe('');
    expect(field('finding').element.value).toBe('');
    scroll.mockRestore();
  });

  it('separates the findings of different linked units and supports manual equipment', async () => {
    const items = [1, 2].map(id => ({
      role: 'serviced', equipment: { id, customer_id: 11, display_name: 'Блок', serial: `SN-${id}` },
    }));
    vi.spyOn(ManagerEquipmentLinksService, 'listManagerOrderEquipmentLinks').mockResolvedValue({ items });
    const wrapper = await mountWorkspace(undefined, {
      ...baseOrder, workflow_type: 'repair', linked_equipment_count: 2,
      repair_meta: { confirmed_facts: ['Утечка в первом блоке'], repair_recommendation: 'Заменить датчик первого блока' },
    });
    const field = (id: string) => wrapper.get<HTMLInputElement>(`[data-testid="repair-${id}"]`);
    expect(field('equipment-selection').element.value).toBe('');
    expect(field('finding').element.value).toBe('');
    expect(wrapper.text()).not.toContain('Подставить рекомендацию из заказа');
    await field('equipment-selection').setValue('Блок · S/N SN-1');
    await field('verdict').setValue('repairable'); await field('finding').setValue('Утечка в первом блоке');
    await field('cost').setValue('220 BYN');
    await field('equipment-selection').setValue('Блок · S/N SN-2');
    expect(field('finding').element.value).toBe('');
    expect(field('cost').element.value).toBe('');
    expect(field('verdict').element.value).toBe('');
    await field('verdict').setValue('operational');
    await field('equipment-selection').setValue('__manual');
    expect(field('equipment').element.value).toBe('');
    expect(field('verdict').element.value).toBe('');
    await wrapper.setProps({ order: { ...baseOrder, id: 45, workflow_type: 'maintenance' } });
    await flushPromises();
    expect(wrapper.find('[data-testid="native-document-type-repair_defect_act"]').exists()).toBe(false);
  });

  it('opens only the saved draft template and gates both shortcuts by template-management access', async () => {
    const draft = { ...revision(77, 'draft'), document_template_id: 19, template_version_id: 22, legal_entity_id: 6 };
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({
      items: [draft, { ...draft, id: 78, status: 'issued' }],
    });
    const wrapper = await mountWorkspace();
    expect(wrapper.find('[data-testid="edit-draft-template"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="edit-selected-template"]').exists()).toBe(false);
    managerSession.auth.value = { capabilities: ['documents.manage'] } as never;
    await flushPromises();
    expect(wrapper.findAll('[data-testid="edit-draft-template"]')).toHaveLength(1);
    expect(wrapper.find('[data-testid="edit-selected-template"]').exists()).toBe(true);
    HTMLDialogElement.prototype.showModal = vi.fn();
    vi.spyOn(ManagerDocumentSystemService, 'getManagerManagedDocumentDraftParameters').mockResolvedValue({
      template_version_id: 22, revision: 'r', has_editable_copy: false, total_amount: '10', issue_date: '2026-10-01',
    });
    await wrapper.get('[data-testid="edit-draft-template"]').trigger('click');
    await vi.dynamicImportSettled();
    await flushPromises();
    expect(ManagerDocumentSystemService.listManagerNativeTemplateVersions).toHaveBeenCalledWith(19, 6);
    expect(ManagerDocumentSystemService.getManagerManagedDocumentDraftParameters).toHaveBeenCalledWith(77);
    await wrapper.setProps({ order: { ...baseOrder, id: 43 } });
    await flushPromises();
    expect(document.querySelector('dialog[aria-labelledby="order-template-editor-title"]')).toBeNull();
  });

  it('keeps customer contract registration behind one compact attachment action', async () => {
    const wrapper = await mountWorkspace();
    await wrapper.get('[data-testid="native-document-type-contract"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="external-contract-form"]').exists()).toBe(false);
    const chooser = wrapper.get('[data-testid="contract-scenario-chooser"]');
    expect(chooser.get('[data-testid="attach-customer-contract"]').text()).toContain('Прикрепить договор');

    await chooser.get('[data-testid="attach-customer-contract"]').trigger('click');
    expect(wrapper.find('[data-testid="external-contract-form"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="native-document-options"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="create-native-draft"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="b2b-contract-terms-panel"]').exists()).toBe(false);
    await wrapper.get('[data-testid="cancel-external-contract"]').trigger('click');
    expect(wrapper.find('[data-testid="create-native-draft"]').exists()).toBe(true);
  });

  it('registers only customer contract metadata and uses it for the next native act', async () => {
    const document = { id: 905, doc_type: 'contract', number: '260930', date: '2026-09-30T00:00:00', is_downloadable: false };
    const register = vi.spyOn(ManagerDocsService, 'registerManagerExternalContract').mockResolvedValue(document);
    const wrapper = await mountWorkspace();
    await wrapper.get('[data-testid="native-document-type-contract"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="attach-customer-contract"]').trigger('click');
    await wrapper.get('[data-testid="external-contract-number"]').setValue(' 260930 ');
    await wrapper.get('[data-testid="external-contract-date"]').setValue('2026-09-30');
    await wrapper.get('[data-testid="external-contract-form"]').trigger('submit');
    await flushPromises();

    expect(register).toHaveBeenCalledWith(42, {
      number: '260930', contract_date: '2026-09-30T00:00:00', external_url: undefined, file: undefined,
    });
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="saved-order-contracts"]').text()).toContain('260930');
    expect(wrapper.emitted('refresh')).toHaveLength(1);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    expect(wrapper.get<HTMLSelectElement>('[data-testid="native-document-basis"]').element.value).toBe('document:905');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42, expect.objectContaining({ document_type: 'act', base_document_id: 905, base_customer_contract_id: null }),
    );
  });

  it('allows a photo and prevents duplicate customer contract submissions', async () => {
    const pending = deferred<never>();
    const register = vi.spyOn(ManagerDocsService, 'registerManagerExternalContract').mockReturnValue(pending.promise as never);
    const wrapper = await mountWorkspace();
    await wrapper.get('[data-testid="native-document-type-contract"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="attach-customer-contract"]').trigger('click');
    await wrapper.get('[data-testid="external-contract-number"]').setValue('260930');
    await wrapper.get('[data-testid="external-contract-date"]').setValue('2026-09-30');
    const file = new File(['photo'], 'contract.jpg', { type: 'image/jpeg' });
    const input = wrapper.get<HTMLInputElement>('[data-testid="external-contract-file"]');
    expect(input.attributes('accept')).toContain('image/jpeg');
    Object.defineProperty(input.element, 'files', { value: [file] });
    await input.trigger('change');
    await wrapper.get('[data-testid="external-contract-form"]').trigger('submit');
    await wrapper.get('[data-testid="external-contract-form"]').trigger('submit');
    expect(register).toHaveBeenCalledTimes(1);
    expect(register).toHaveBeenCalledWith(42, expect.objectContaining({ file }));
    expect(wrapper.get('[data-testid="save-external-contract"]').attributes('disabled')).toBeDefined();
  });

  it.each(['offer', 'contract'])('prefers a saved customer contract over an older native %s after reopening', async (documentType) => {
    const nativeDocument = { id: 904, order_id: 42, legal_entity_id: 5, doc_type: documentType, status: 'issued', provider: 'native', display_number: 'OLD', date: NOW, created_at: NOW, artifacts: [] };
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [nativeDocument as never] });
    const order = {
      ...baseOrder, customer_contract_id: null, customer_contract: null,
      documents: [
        { id: 904, doc_type: documentType, number: 'OLD', date: NOW },
        { id: 905, doc_type: 'contract', number: '260930', date: '2026-09-30T00:00:00', is_downloadable: false },
      ],
    };
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    const basis = wrapper.get<HTMLSelectElement>('[data-testid="native-document-basis"]');
    expect(basis.element.value).toBe('document:905');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenLastCalledWith(
      42, expect.objectContaining({ base_document_id: 905, base_customer_contract_id: null }),
    );

    await basis.setValue('document:904');
    await wrapper.setProps({ order: { ...order, documents: [...order.documents,
      { id: 907, doc_type: 'contract', number: 'ANOTHER', date: NOW },
    ] } });
    await flushPromises();
    expect(basis.element.value).toBe('document:904');
  });

  it('allows metadata registration without legal entity templates and keeps failed data', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockResolvedValue({ items: [] });
    const register = vi.spyOn(ManagerDocsService, 'registerManagerExternalContract').mockRejectedValue(new Error('Временно недоступно'));
    const wrapper = await mountWorkspace();
    await wrapper.get('[data-testid="native-document-type-contract"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="attach-customer-contract"]').trigger('click');
    await wrapper.get('[data-testid="external-contract-form"]').trigger('submit');
    expect(register).not.toHaveBeenCalled();
    await wrapper.get('[data-testid="external-contract-number"]').setValue('260930');
    await wrapper.get('[data-testid="external-contract-date"]').setValue('2026-09-30');
    await wrapper.get('[data-testid="external-contract-form"]').trigger('submit');
    await flushPromises();
    expect(wrapper.get<HTMLInputElement>('[data-testid="external-contract-number"]').element.value).toBe('260930');
    expect(wrapper.get('[data-testid="external-contract-form"]').exists()).toBe(true);
    expect(wrapper.emitted('refresh')).toBeUndefined();
  });

  it('does not offer native draft or void contracts as external act bases', async () => {
    const draft = { id: 906, order_id: 42, legal_entity_id: 5, doc_type: 'contract', status: 'draft', provider: 'native', display_number: 'draft', date: NOW, created_at: NOW, artifacts: [] };
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [draft as never] });
    const wrapper = await mountWorkspace(undefined, {
      ...baseOrder, customer_contract_id: null, customer_contract: null,
      documents: [{ id: 906, doc_type: 'contract', number: 'draft', date: NOW }],
    });
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="native-document-basis"]').text()).not.toContain('draft');
    expect(wrapper.find('[data-testid="saved-order-contracts"]').exists()).toBe(false);
  });

  it('loads templates once when the default legal entity is selected', async () => {
    await mountWorkspace();

    expect(ManagerDocumentSystemService.listManagerNativeDocumentTemplates).toHaveBeenCalledTimes(1);
  });

  it('uses a human label when a native document has no official number', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({
      items: [{
        id: 88,
        order_id: 42,
        legal_entity_id: 5,
        doc_type: 'contract',
        status: 'issued',
        provider: 'native',
        internal_reference: 'doc_8c0d3f',
        display_number: 'doc_8c0d3f',
        date: NOW,
        created_at: NOW,
        artifacts: [],
      }],
    });
    const wrapper = await mountWorkspace();

    const title = wrapper.findAll('h4').find((item) => item.text().includes('Договор'));
    expect(title?.text()).toBe('Договор · номер ещё не присвоен');
    expect(title?.text()).not.toContain('doc_8c0d3f');
  });

  it.each(['contract', 'b2c_supply_installation_act', 'maintenance_defect_act'])('keeps the complete %s replacement chain collapsed under its current document', async (type) => {
    const oldest = { ...revision(81, 'void', null, type), void_reason: 'Ошибка в реквизитах' };
    const replaced = revision(82, 'replaced', 81, type);
    const current = revision(83, 'issued', 82, type);
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [current, replaced, oldest] });
    const wrapper = await mountWorkspace();
    expect(wrapper.findAll('article')).toHaveLength(1);
    expect(wrapper.get('[data-testid="current-document-83"]').text()).toContain('Д-2026-83');
    const history = wrapper.get('[data-testid="previous-versions-83"]');
    expect(history.get('summary').text()).toBe('Предыдущие версии (2)');
    expect(history.attributes('open')).toBeUndefined();
    expect(history.findAll('li').map((item) => item.attributes('data-testid'))).toEqual(['historical-document-82', 'historical-document-81']);
    expect(history.text()).toContain('Заменён');
    expect(history.text()).toContain('Причина аннулирования: Ошибка в реквизитах');
    expect(history.findAll('button').some((button) => button.text().includes('Создать исправленную редакцию'))).toBe(false);
    expect(wrapper.find('[data-testid="native-document-history"]').exists()).toBe(false);
  });

  it('keeps the issued original current while its correction is only a draft', async () => {
    const current = revision(82, 'issued', 81);
    const draft = revision(83, 'draft', 82);
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [draft, current, revision(81, 'replaced')] });
    const wrapper = await mountWorkspace();
    expect(wrapper.findAll('article')).toHaveLength(2);
    expect(wrapper.find('[data-testid="previous-versions-83"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="previous-versions-82"]').text()).toContain('Д-2026-81');

    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [revision(83, 'issued', 82), revision(82, 'replaced', 81), revision(81, 'replaced')] });
    vi.mocked(ManagerDocumentSystemService.issueManagerManagedDocument).mockResolvedValue(revision(83, 'issued', 82));
    await wrapper.get('[data-testid="current-document-83"]').findAll('button').find((button) => button.text() === 'Выпустить')!.trigger('click');
    await flushPromises();
    expect(wrapper.findAll('article')).toHaveLength(1);
    expect(wrapper.get('[data-testid="previous-versions-83"] summary').text()).toBe('Предыдущие версии (2)');
  });

  it('retains cancelled documents without an active successor in a collapsed order history', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [revision(81, 'void'), revision(82, 'replaced', 999)] });
    const wrapper = await mountWorkspace();
    expect(wrapper.findAll('article')).toHaveLength(0);
    const history = wrapper.get('[data-testid="native-document-history"]');
    expect(history.get('summary').text()).toBe('История документов (2)');
    expect(history.attributes('open')).toBeUndefined();
    expect(history.findAll('li')).toHaveLength(2);
    expect(wrapper.text()).not.toContain('Внутренних документов пока нет');
  });

  it('retains historical files and emits their original IDs for download without mutation actions', async () => {
    const previous = {
      ...revision(81, 'replaced'),
      artifacts: ['pdf', 'rendered_docx', 'source_docx'].map((kind) => ({
        id: `file-${kind}`, order_document_id: 81, kind, content_type: 'application/octet-stream',
        filename: `${kind}.file`, checksum_sha256: 'a'.repeat(64), size_bytes: 100, created_at: NOW,
      })),
    };
    const wrapper = mount(DocumentVersionHistory, { props: { documents: [previous] } });
    wrappers.push(wrapper);
    const details = wrapper.get('details').element as HTMLDetailsElement;
    details.open = true;
    await wrapper.get('details').trigger('toggle');
    const buttons = wrapper.findAll('button');
    expect(buttons.map((button) => button.text().replace('download', '').trim())).toEqual(['PDF', 'DOCX', 'Исходный DOCX']);
    await buttons[0]!.trigger('click');
    expect(wrapper.emitted('download')).toEqual([['file-pdf', 'pdf.file']]);
  });

  it('does not lose historical documents when saved links are missing or cyclic', () => {
    const grouped = groupDocumentVersions([revision(83, 'issued', 82), revision(82, 'replaced', 81), revision(81, 'void', 82), revision(80, 'void', 999)]);
    expect(grouped.current[0]!.previousVersions.map((item) => item.id)).toEqual([82, 81]);
    expect(grouped.archived.map((item) => item.id)).toEqual([80]);
  });

  it('waits for the order-save barrier before creating a native draft', async () => {
    const barrier = deferred<{ mutated: boolean }>();
    const beforeGenerate = vi.fn(() => barrier.promise);
    const wrapper = await mountWorkspace(beforeGenerate);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();

    expect(wrapper.get('[data-testid="create-native-draft"]').attributes('data-order-usage')).toBe('document_create');

    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(beforeGenerate).toHaveBeenCalledWith('act');
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();

    barrier.resolve({ mutated: true });
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({ document_type: 'act' }),
    );
  });

  it('does not create a native draft when the parent blocks unsaved manual changes', async () => {
    const beforeGenerate = vi.fn().mockResolvedValue(false);
    const wrapper = await mountWorkspace(beforeGenerate);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();

    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();

    expect(beforeGenerate).toHaveBeenCalledWith('act');
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
    expect(wrapper.emitted('toast')).toContainEqual([expect.objectContaining({
      type: 'error',
      message: expect.stringContaining('Сначала сохраните изменения'),
    })]);
  });

  it('prefills the document city from the default seller legal entity', async () => {
    const wrapper = await mountWorkspace();

    expect(wrapper.get<HTMLInputElement>('[data-testid="native-document-issue-city"]').element.value)
      .toBe('Витебск');
  });

  it('asks a regular manager to contact the account owner when Google is disconnected', async () => {
    const wrapper = await mountWorkspace();

    const notice = wrapper.get('[data-testid="document-google-disconnected"]');
    expect(notice.text()).toContain('обратитесь к владельцу аккаунта');
    expect(notice.find('button').exists()).toBe(false);
  });

  it('deletes an unissued draft after an explicit confirmation', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValueOnce({
        items: [{
          id: 77,
          order_id: 42,
          legal_entity_id: 5,
          doc_type: 'contract',
          status: 'draft',
          provider: 'native',
          internal_reference: 'doc_draft_77',
          display_number: 'doc_draft_77',
          date: NOW,
          created_at: NOW,
          artifacts: [],
        }],
      })
      .mockResolvedValue({ items: [] });
    const wrapper = await mountWorkspace();

    const remove = wrapper.findAll('button').find((button) => button.text() === 'Удалить черновик');
    expect(remove).toBeDefined();
    await remove!.trigger('click');
    await flushPromises();

    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Удалить черновик?',
      variant: 'danger',
    }));
    expect(ManagerDocumentSystemService.deleteManagerManagedDocumentDraft).toHaveBeenCalledWith(77);
  });

  it('deletes an unissued Google draft with source files after confirmation', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValueOnce({
        items: [{
          id: 77,
          order_id: 42,
          legal_entity_id: 5,
          doc_type: 'contract',
          status: 'draft',
          provider: 'native',
          internal_reference: 'doc_draft_77',
          display_number: 'doc_draft_77',
          date: NOW,
          created_at: NOW,
          artifacts: [{ id: 'source-77', kind: 'source_docx', filename: 'draft.docx', is_authoritative: true }],
        }],
      })
      .mockResolvedValue({ items: [] });
    const wrapper = await mountWorkspace();

    const remove = wrapper.findAll('button').find((button) => button.text() === 'Удалить черновик');
    expect(remove).toBeDefined();
    await remove!.trigger('click');
    await flushPromises();

    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Удалить черновик?',
      variant: 'danger',
    }));
    expect(ManagerDocumentSystemService.deleteManagerManagedDocumentDraft).toHaveBeenCalledWith(77);
  });

  it('opens a PDF preview for a draft without issuing a number', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({
      items: [{
        id: 77,
        order_id: 42,
        legal_entity_id: 5,
        doc_type: 'contract',
        status: 'draft',
        provider: 'native',
        internal_reference: 'doc_draft_77',
        display_number: 'doc_draft_77',
        date: NOW,
        created_at: NOW,
        artifacts: [],
      }],
    });
    const wrapper = await mountWorkspace();

    const preview = wrapper.findAll('button').find((button) => button.text().includes('Предпросмотр'));
    expect(preview).toBeDefined();
    await preview!.trigger('click');
    await flushPromises();

    expect(openNativeDocumentPreview).toHaveBeenCalledWith(77);
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
  });

  it('offers Google editing for drafts and keeps issued documents immutable', async () => {
    vi.mocked(googleDocumentEditorApi.getConnectionStatus).mockResolvedValue({
      connected: true,
      provider: 'google_drive',
      account_label: 'manager@example.com',
      managed_folder_url: 'https://drive.google.com/drive/folders/crm',
      connected_at: NOW,
      last_verified_at: NOW,
      last_error_code: null,
    });
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({
      items: [{
        id: 77,
        order_id: 42,
        legal_entity_id: 5,
        doc_type: 'contract',
        status: 'draft',
        provider: 'native',
        internal_reference: 'doc_draft_77',
        display_number: 'doc_draft_77',
        date: NOW,
        created_at: NOW,
        artifacts: [],
      }, {
        id: 78,
        order_id: 42,
        legal_entity_id: 5,
        doc_type: 'contract',
        status: 'issued',
        provider: 'native',
        official_number: '12',
        display_number: 'D-2026-12',
        date: NOW,
        created_at: NOW,
        artifacts: [],
      }],
    });
    const replace = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue({ opener: null, location: { replace }, close: vi.fn() } as never);
    const wrapper = await mountWorkspace();

    expect(wrapper.get('[data-testid="document-google-connected"]').text()).toContain('manager@example.com');
    expect(wrapper.findAll('button').filter((button) => button.text().includes('Редактировать в Google Docs'))).toHaveLength(1);
    expect(wrapper.findAll('button').some((button) => button.text() === 'Создать исправленную редакцию')).toBe(true);

    const edit = wrapper.findAll('button').find((button) => button.text().includes('Редактировать в Google Docs'))!;
    await edit.trigger('click');
    await flushPromises();
    expect(googleDocumentEditorApi.createSession).toHaveBeenCalledWith({ kind: 'managed-document', documentId: 77 });
    expect(replace).toHaveBeenCalledWith('https://docs.google.com/document/d/document-77/edit');

    vi.mocked(googleDocumentEditorApi.getSession).mockResolvedValue({
      id: 'document-session-77',
      status: 'changed',
      edit_url: 'https://docs.google.com/document/d/document-77/edit',
      can_edit: true,
      base_checksum_sha256: 'a'.repeat(64),
      remote_revision: 'revision-2',
      modified_at: NOW,
      last_synced_at: NOW,
      detail: null,
    });
    window.dispatchEvent(new Event('focus'));
    await flushPromises();
    await flushPromises();

    expect(googleDocumentEditorApi.syncSession).toHaveBeenCalledWith({ kind: 'managed-document', documentId: 77 });
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('истории документа'))).toBe(true);
  });

  it('offers CRM email only to the system tenant until partner mail is connected', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({
      items: [{
        id: 78,
        order_id: 42,
        legal_entity_id: 5,
        doc_type: 'contract',
        status: 'issued',
        provider: 'native',
        official_number: '12',
        display_number: 'D-2026-12',
        date: NOW,
        created_at: NOW,
        artifacts: [],
      }],
    });
    managerSession.auth.value = { is_system_tenant: true } as never;
    const wrapper = await mountWorkspace();

    expect(wrapper.find('[data-testid="native-document-email"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="native-email-unavailable"]').exists()).toBe(false);

    managerSession.auth.value = { is_system_tenant: false } as never;
    await flushPromises();
    expect(wrapper.find('[data-testid="native-document-email"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="native-email-unavailable"]').text())
      .toContain('почты вашей организации');
  });

  it.each([
    { documentType: 'act', override: 'seller_payer' },
    { documentType: 'invoice', override: 'executor_payer' },
  ])('inherits party names by default and submits the $override override for $documentType', async ({ documentType, override }) => {
    const wrapper = await mountWorkspace();
    await wrapper.get(`[data-testid="native-document-type-${documentType}"]`).trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="native-document-party-roles"]').text()).toContain('Как в договоре');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenLastCalledWith(
      42, expect.objectContaining({ document_role_type: documentType === 'invoice' ? 'seller_buyer' : null, base_customer_contract_id: 91 }),
    );
    const partyRoles = wrapper.get('[data-testid="native-document-party-roles"]');
    expect(partyRoles.text()).toContain(override === 'seller_payer' ? 'Продавец / Плательщик' : 'Исполнитель / Плательщик');
    await partyRoles.setValue(override);
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenLastCalledWith(
      42, expect.objectContaining({ document_role_type: override }),
    );
    await wrapper.get(`[data-testid="native-document-type-${documentType === 'act' ? 'invoice' : 'act'}"]`).trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenLastCalledWith(
      42, expect.objectContaining({ document_role_type: documentType === 'act' ? 'seller_buyer' : null }),
    );
  });

  it('uses the active customer contract as the default basis for an act', async () => {
    const wrapper = await mountWorkspace();

    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();

    expect(wrapper.get('[data-testid="native-document-basis"]').element).toHaveProperty(
      'value',
      'customer-contract:91',
    );
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();

    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        document_type: 'act',
        proposal_id: 7,
        base_document_id: null,
        base_customer_contract_id: 91,
        act_terms: expect.objectContaining({ claims_status: 'none' }),
      }),
    );
  });

  it('uses an unbound open contract, verified roles, selected site and partial works of the current proposal', async () => {
    const openContract = { ...baseOrder.customer_contract!, id: 92, number: 'ОД-2026-001', created_at: NOW, document_role_type: undefined };
    vi.mocked(ManagerContractsService.getManagerCustomerContracts).mockResolvedValue({ items: [
      openContract,
      { ...openContract, id: 93, number: 'Архивный', status: 'archived' },
      { ...openContract, id: 94, number: 'Истёкший', valid_until: '2020-01-01' },
      { ...openContract, id: 95, number: 'Будущий', valid_from: '2099-01-01' },
      { ...openContract, id: 96, number: 'Чужой', customer_id: 99 },
    ] });
    vi.mocked(ManagerService.getManagerCustomerBranches).mockResolvedValue({ items: [
      { id: 31, customer_id: 11, name: 'Магазин', delivery_address: 'Витебск, ул. Кирова, 2' },
    ] });
    const otherLine = { id: 46, proposal_id: 7, service_title: 'ТО кондиционера', quantity: 5, price: 20, line_total: 100 };
    const proposal = baseOrder.proposals![0]!;
    const order = { ...baseOrder, customer_contract_id: null, customer_contract: null,
      service_lines: [{ ...otherLine, id: 48, proposal_id: 8, service_title: 'Другая смета' }],
      proposals: [{ ...proposal, service_lines: [...proposal.service_lines!, otherLine] }],
    };
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    const basis = wrapper.get<HTMLSelectElement>('[data-testid="native-document-basis"]');
    expect(basis.findAll('option')).toHaveLength(2);
    expect(basis.element.value).toBe('customer-contract:92');
    const create = wrapper.get('[data-testid="create-native-draft"]');
    expect(create.attributes('disabled')).toBeDefined();
    await wrapper.get('[data-testid="native-document-party-roles"]').setValue('executor_customer');
    await wrapper.get('[data-testid="act-site"]').setValue('31');
    const composition = wrapper.get('[data-testid="native-act-composition"]');
    expect(composition.text()).not.toContain('Другая смета');
    await composition.get('input[type="checkbox"][aria-label="Диагностика"]').setValue(false);
    await composition.get('input[aria-label="Количество: ТО кондиционера"]').setValue('2');
    await wrapper.setProps({ order: { ...order, proposals: structuredClone(order.proposals) } });
    await create.trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42, expect.objectContaining({
      base_customer_contract_id: 92, document_role_type: 'executor_customer', proposal_id: 7,
      scope_customer_branch_id: 31, scope_title: 'Магазин', scope_address: 'Витебск, ул. Кирова, 2',
      scope_service_line_ids: [46], scope_service_line_quantities: { 46: 2 },
    }));
    await composition.get('input[type="checkbox"][aria-label="ТО кондиционера"]').setValue(false);
    expect(create.attributes('title')).toContain('Выберите хотя бы одну');
    expect(create.attributes('disabled')).toBeDefined();
  });

  it('asks which unbound open contract to use and preserves a manual choice across reloads', async () => {
    const item = { ...baseOrder.customer_contract!, document_role_type: 'executor_customer', created_at: NOW };
    vi.mocked(ManagerContractsService.getManagerCustomerContracts).mockResolvedValue({ items: [
      item, { ...item, id: 92, number: 'Второй' },
    ] });
    const order = { ...baseOrder, customer_contract_id: null, customer_contract: null };
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    const field = wrapper.get<HTMLSelectElement>('[data-testid="native-document-basis"]');
    expect(field.element.value).toBe('');
    expect(wrapper.get('[data-testid="create-native-draft"]').attributes('disabled')).toBeDefined();
    await field.setValue('customer-contract:92');
    await wrapper.setProps({ order: { ...order, documents: [] } });
    expect(field.element.value).toBe('customer-contract:92');
    await wrapper.get('[data-testid="native-document-issue-date"]').setValue('2100-01-01');
    expect(field.element.value).toBe('');
    expect(wrapper.get('[data-testid="create-native-draft"]').attributes('disabled')).toBeDefined();
  });

  it('filters registry contracts by issuer, deduplicates their order documents and routes unresolved issuers to the customer', async () => {
    const seller = { tenant_id: 1, status: 'active', requisites: {}, created_at: NOW, updated_at: NOW };
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockResolvedValue({ items: [
      { ...seller, id: 5, display_name: 'Первый', is_default: true },
      { ...seller, id: 7, display_name: 'Второй', is_default: false },
    ] } as never);
    const contract = { ...baseOrder.customer_contract!, created_at: NOW, legal_entity_id: 5, source_document_id: 901 };
    vi.mocked(ManagerContractsService.getManagerCustomerContracts).mockResolvedValue({ items: [
      contract, { ...contract, id: 92, number: 'Другой исполнитель', legal_entity_id: 7, source_document_id: 902 },
      { ...contract, id: 93, number: 'Не указан исполнитель', legal_entity_id: null, source_document_id: null },
      { ...contract, id: 94, number: 'Архивный договор', status: 'archived', source_document_id: 904 },
    ] } as never);
    const native = [901, 902, 904].map((id) => ({ ...revision(id, 'issued'), legal_entity_id: id === 902 ? 7 : 5 }));
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: native });
    const order = { ...baseOrder, customer_contract: null, customer_contract_id: null, documents:
      native.map(item => ({ id: item.id, doc_type: 'contract', number: item.display_number, date: NOW })) };
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    const selector = wrapper.get<HTMLSelectElement>('[data-testid="native-document-basis"]');
    expect(selector.findAll('option').map(o => o.element.value)).toEqual(['', 'customer-contract:91']);
    expect(selector.element.value).toBe('');
    await selector.setValue('customer-contract:91');
    const link = wrapper.get('[data-testid="verify-contract-issuer"]');
    const url = new URL(link.attributes('href')!, window.location.origin);
    expect(url.searchParams.get('customerId')).toBe('11');
    expect(url.searchParams.get('section')).toBe('documents');
    expect(url.searchParams.get('editContractId')).toBe('93');
    await wrapper.get('[data-testid="native-legal-entity"]').setValue('7');
    expect(selector.findAll('option').map(o => o.element.value)).toEqual(['', 'customer-contract:92']);
    await link.trigger('click');
    vi.mocked(ManagerContractsService.getManagerCustomerContracts).mockResolvedValue({ items: [
      { ...contract, id: 93, legal_entity_id: 7, source_document_id: null },
    ] } as never);
    window.dispatchEvent(new Event('focus')); await flushPromises();
    expect(wrapper.find('[data-testid="verify-contract-issuer"]').exists()).toBe(false);
    expect(selector.text()).toContain(contract.number);
  });

  it('discards a late contract list after switching customers or accounts', async () => {
    const first = deferred<{ items: never[] }>();
    const lookup = vi.mocked(ManagerContractsService.getManagerCustomerContracts)
      .mockReturnValueOnce(first.promise as never)
      .mockResolvedValue({ items: [] });
    const order = { ...baseOrder, customer_contract_id: null, customer_contract: null };
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    const nextOrder = { ...order, customer: { ...order.customer!, id: 12 } };
    await wrapper.setProps({ order: nextOrder });
    await flushPromises();
    expect(lookup).toHaveBeenLastCalledWith(12);
    managerSession.auth.value = { tenant_id: 2, storefront_id: 4 } as never;
    await flushPromises();
    const before = lookup.mock.calls.length;
    first.resolve({ items: [{ ...baseOrder.customer_contract, number: 'Предыдущий клиент' }] as never[] });
    await flushPromises();
    expect(lookup).toHaveBeenCalledTimes(before);
    expect(wrapper.get('[data-testid="native-document-basis"]').text()).not.toContain('Предыдущий клиент');
    expect(wrapper.get('[data-testid="create-native-draft"]').attributes('disabled')).toBeDefined();
  });

  it('never takes works from another proposal if the selected proposal has no works', async () => {
    const first = baseOrder.proposals![0]!;
    const wrapper = await mountWorkspace(undefined, {
      ...baseOrder, proposals: [first, { ...first, id: 8, service_lines: [], is_selected: false }],
      service_lines: first.service_lines,
    });
    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await wrapper.setProps({ activeProposalId: 8 });
    await flushPromises();
    expect(wrapper.get('[data-testid="native-act-composition"]').text()).toContain('нет работ');
    expect(wrapper.get('[data-testid="create-native-draft"]').attributes('disabled')).toBeDefined();
  });

  it('requires remarks text when an act is created with customer remarks', async () => {
    const wrapper = await mountWorkspace();

    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="act-claims-present"]').trigger('click');

    expect(wrapper.get('[data-testid="create-native-draft"]').attributes('title'))
      .toContain('Опишите замечания заказчика');
    await wrapper.get('[data-testid="act-claims-text"]').setValue('Устранить шум наружного блока.');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();

    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        act_terms: expect.objectContaining({
          claims_status: 'present',
          claims_text: 'Устранить шум наружного блока.',
        }),
      }),
    );
  });

  it('shows the invoice role as a direct two-state switch', async () => {
    const wrapper = await mountWorkspace();

    await wrapper.get('[data-testid="native-document-type-invoice"]').trigger('click');
    await flushPromises();

    const toggle = wrapper.get('[data-testid="invoice-role-toggle"]');
    expect(toggle.findAll('button').map((button) => button.text())).toEqual([
      'Документ для оплаты',
      'Счёт-оферта',
    ]);
    await toggle.findAll('button')[1]!.trigger('click');
    expect(toggle.text()).toContain('Счёт-оферта');
  });

  it('starts with an offer and suggests the contract scenario from the order workflow', async () => {
    const wrapper = await mountWorkspace();
    expect(wrapper.get('[data-testid="native-document-type-offer"]').attributes('aria-pressed')).toBe('true');
    await wrapper.get('[data-testid="native-document-type-contract"]').trigger('click');
    await flushPromises();
    expect(wrapper.findAll('button[data-testid^="contract-scenario-"]')).toHaveLength(7);
    expect(wrapper.get('[data-testid="contract-scenario-supply_installation"]').attributes('aria-pressed')).toBe('true');

    await wrapper.get('[data-testid="contract-scenario-supply_installation"]').trigger('click');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();

    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        document_type: 'contract',
        issue_city: 'Витебск',
        business_terms: expect.objectContaining({
          contract_scenario: 'supply_installation',
          goods_warranty_months: 48,
          payment_schedule: expect.arrayContaining([
            expect.objectContaining({ share_percent: 100, due_event: 'before_supply' }),
          ]),
        }),
      }),
    );
  });

  it('prefers a maintenance template and executor roles for a maintenance order', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerNativeDocumentTemplates).mockImplementation(
      async (_legalEntityId, documentType) => ({ items: documentType === 'contract' ? [
        { id: 120, tenant_id: 1, legal_entity_id: 5, name: 'Универсальный', doc_type: 'contract', is_default: true, is_active: true, sort_order: 0, created_at: NOW },
        { id: 121, tenant_id: 1, legal_entity_id: 5, name: 'Техническое обслуживание', doc_type: 'contract', contract_scenario: 'maintenance', is_default: false, is_active: true, sort_order: 1, created_at: NOW },
      ] : [{ id: 100, tenant_id: 1, legal_entity_id: 5, name: 'КП', doc_type: documentType || 'offer', is_default: true, is_active: true, sort_order: 0, created_at: NOW }] }),
    );
    const wrapper = await mountWorkspace(undefined, { ...baseOrder, workflow_type: 'maintenance' });
    await wrapper.get('[data-testid="native-document-type-contract"]').trigger('click');
    await flushPromises();

    expect(wrapper.get('[data-testid="contract-scenario-maintenance"]').attributes('aria-pressed')).toBe('true');
    expect(wrapper.get<HTMLSelectElement>('[data-testid="native-document-party-roles"]').element.value).toBe('executor_customer');
    expect(wrapper.get<HTMLSelectElement>('[data-testid="native-document-template"]').element.value).toBe('121');
    expect(wrapper.get('[data-testid="warranty-terms-details"]').text()).toContain('оборудование не указано');
  });

  it('sends B2C terms only for a consumer order document', async () => {
    const wrapper = await mountWorkspace();

    expect(wrapper.find('[data-testid="native-document-type-b2c_route_laying_act"]').exists()).toBe(false);
    await wrapper.get('[data-testid="native-audience-consumer"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="native-document-type-b2c_route_laying_act"]').exists()).toBe(true);

    await wrapper.get('[data-testid="native-document-type-b2c_route_laying_act"]').trigger('click');
    await flushPromises();

    expect(wrapper.get('[data-testid="consumer-document-terms"]').text())
      .toContain('Параметры закладки трассы');
    expect(wrapper.get('[data-testid="consumer-document-terms"]').text())
      .not.toContain('Гарантия на оборудование');
    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-work-warranty"]').element.value)
      .toBe('12');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();

    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        document_type: 'b2c_route_laying_act',
        consumer_terms: expect.objectContaining({
          goods_warranty_months: 36,
          work_warranty_months: 12,
        }),
      }),
    );
  });

  it('keeps entered order facts when the seller changes', async () => {
    const firstEntity = (await ManagerDocumentSystemService.listManagerDocumentLegalEntities()).items[0]!;
    vi.mocked(ManagerDocumentSystemService.listManagerDocumentLegalEntities).mockResolvedValue({
      items: [
        firstEntity,
        {
          ...firstEntity,
          id: 6,
          slug: 'partner',
          display_name: 'ИП Партнёр',
          is_default: false,
          requisites: {
            ...firstEntity.requisites,
            default_goods_warranty_months: '24',
          },
        },
      ],
    });
    const wrapper = await mountWorkspace();

    await wrapper.get('[data-testid="native-audience-consumer"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="native-document-type-b2c_supply_installation_act"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="consumer-equipment-brand"]').setValue('Midea');
    await wrapper.get('[data-testid="consumer-goods-warranty"]').setValue('60');
    await wrapper.get('[data-testid="native-legal-entity"]').setValue('6');
    await flushPromises();

    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-equipment-brand"]').element.value)
      .toBe('Midea');
    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-goods-warranty"]').element.value)
      .toBe('60');
  });

  it('blocks draft creation while a newly selected document type is loading', async () => {
    const pendingAct = deferred<Awaited<ReturnType<
      typeof ManagerDocumentSystemService.listManagerNativeDocumentTemplates
    >>>();
    vi.mocked(ManagerDocumentSystemService.listManagerNativeDocumentTemplates)
      .mockImplementation(async (_legalEntityId, documentType) => {
        if (documentType === 'act') return pendingAct.promise;
        return {
          items: [{
            id: 100,
            tenant_id: 1,
            legal_entity_id: 5,
            name: 'Шаблон договора',
            doc_type: documentType || 'contract',
            is_default: true,
            is_active: true,
            sort_order: 0,
            created_at: NOW,
          }],
        };
      });
    const wrapper = await mountWorkspace();

    await wrapper.get('[data-testid="native-document-type-act"]').trigger('click');
    const create = wrapper.get('[data-testid="create-native-draft"]');
    expect(create.attributes('disabled')).toBeDefined();
    expect(create.attributes('title')).toContain('Загружаем подходящий шаблон');
    await create.trigger('click');
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();

    pendingAct.resolve({ items: [] });
    await flushPromises();
    expect(create.attributes('title')).toContain('Нет шаблона');
  });
});


describe('Selected native customer requirements', () => {
  const missing = { checked: true, can_issue: false,
    missing_fields: [{ field: 'customer.legal_address', label: 'Юридический адрес клиента', critical: true }],
    template_id: 100, template_version_id: 101 };

  const chooseDocument = async (wrapper: VueWrapper, documentType = 'contract') => {
    await wrapper.get(`[data-testid="native-document-type-${documentType}"]`).trigger('click');
    await flushPromises();
    const action = wrapper.findAll('button').find((button) => button.text().includes('Создать наш договор'));
    if (action) await action.trigger('click');
    await flushPromises();
  };

  it.each([
    { documentType: 'contract', canIssue: false }, { documentType: 'act', canIssue: true },
  ])('creates a $documentType on the first click after checking the actual template', async ({ documentType, canIssue }) => {
    vi.mocked(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).mockResolvedValue({ ...missing, can_issue: canIssue });
    const pending = deferred<ManagedDocumentItem>();
    vi.mocked(ManagerDocumentSystemService.createManagerManagedDocumentDraft).mockReturnValue(pending.promise as never);
    const wrapper = await mountWorkspace();
    await chooseDocument(wrapper, documentType);
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    const warning = wrapper.get('[data-testid="native-customer-readiness-warning"]');
    expect(warning.text()).toContain('Можно вписать от руки');
    expect(warning.text()).toContain('Юридический адрес клиента');
    expect(warning.text()).not.toContain('Основание полномочий');
    expect(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).toHaveBeenCalledTimes(1);
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42,
      expect.objectContaining({ document_type: documentType, allow_incomplete_customer: !canIssue }));
    pending.resolve(revision(77, 'draft', null, documentType)); await flushPromises();
    expect(confirmDialog).not.toHaveBeenCalled();
  });

  it.each(['contract', 'act'])('discards a preflight response when the selected context changes in flight for %s', async (documentType) => {
    const barrier = deferred<typeof missing>();
    vi.mocked(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).mockReturnValue(barrier.promise as never);
    const wrapper = await mountWorkspace();
    await chooseDocument(wrapper, documentType);
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="native-document-issue-city"]').setValue('Минск');
    barrier.resolve(missing);
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="native-customer-readiness-warning"]').exists()).toBe(false);
  });

  it.each(['contract', 'act'])('discards delayed preflight when saved customer or signing mode changes for %s', async (documentType) => {
    const barrier = deferred<typeof missing>();
    vi.mocked(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).mockReturnValue(barrier.promise as never);
    const wrapper = await mountWorkspace();
    await chooseDocument(wrapper, documentType);
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    await wrapper.setProps({ order: { ...baseOrder, customer: { ...baseOrder.customer, signing_mode: 'power_of_attorney' } } });
    barrier.resolve(missing);
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="native-customer-readiness-warning"]').exists()).toBe(false);
  });

  it.each(['contract', 'invoice', 'act', 'repair_defect_act', 'retail_receipt', 'warranty_certificate'])(
    'issues the original %s from a legacy draft with missing details and keeps the printed-field hint after issue', async (documentType) => {
      const original = { ...revision(77, 'draft', null, documentType), customer_readiness: missing };
      vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
        .mockResolvedValueOnce({ items: [original] })
        .mockResolvedValue({ items: [{ ...original, status: 'issued', customer_readiness: { ...missing, can_issue: true } }] });
      vi.mocked(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).mockResolvedValue(missing);
      const wrapper = await mountWorkspace();
      const card = wrapper.get('[data-testid="current-document-77"]');
      const hint = () => card.get('[data-testid="native-manual-fields"]');
      expect(hint().text()).toContain('Юридический адрес клиента');
      expect(hint().find('button').text()).toBe('Открыть карточку клиента');
      const issue = card.findAll('button').find(button => button.text() === 'Выпустить')!;
      expect(issue.attributes('disabled')).toBeUndefined();
      await issue.trigger('click'); await flushPromises();
      expect(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).toHaveBeenCalledWith(77);
      expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
      expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
      expect(confirmDialog).not.toHaveBeenCalled();
      expect(card.text()).toContain('Выпущен');
      expect(hint().text()).toContain('Можно вписать от руки');
    });

  it('reads a draft without cached readiness and retains the authoritative fields returned after issue', async () => {
    const original = revision(77, 'draft', null, 'act');
    const advisory = { ...missing, can_issue: true, missing_fields: [
      { field: 'customer.signer_name', label: 'ФИО подписанта клиента', critical: false },
    ] };
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValueOnce({ items: [original] })
      .mockResolvedValue({ items: [{ ...original, status: 'issued', customer_readiness: advisory }] });
    vi.mocked(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).mockResolvedValue(advisory);
    const wrapper = await mountWorkspace();
    const card = wrapper.get('[data-testid="current-document-77"]');
    expect(card.find('[data-testid="native-manual-fields"]').exists()).toBe(false);
    await card.findAll('button').find(button => button.text() === 'Выпустить')!.trigger('click'); await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
    expect(card.get('[data-testid="native-manual-fields"]').text()).toContain('ФИО подписанта клиента');
  });

  it('leaves a saved draft intact on a readiness network error and allows retry', async () => {
    const original = { ...revision(77, 'draft', null, 'act'), customer_readiness: missing };
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [original] });
    vi.mocked(ManagerDocumentSystemService.getManagerManagedDocumentReadiness)
      .mockRejectedValueOnce(new Error('Сеть недоступна'))
      .mockResolvedValue({ ...missing, can_issue: true });
    const wrapper = await mountWorkspace();
    const issue = wrapper.get('[data-testid="current-document-77"]').findAll('button').find(button => button.text() === 'Выпустить')!;
    await issue.trigger('click'); await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
    expect(wrapper.emitted('toast')?.some(([event]) => event.message.includes('Сеть недоступна'))).toBe(true);
    await issue.trigger('click'); await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
  });

  it('does not override a negative preflight without missing customer fields', async () => {
    vi.mocked(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness)
      .mockResolvedValue({ ...missing, missing_fields: [] });
    const wrapper = await mountWorkspace();
    await chooseDocument(wrapper, 'act');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click'); await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
  });

  const issueDraft = {
    id: 77, order_id: 42, legal_entity_id: 5, doc_type: 'contract', status: 'draft', provider: 'native',
    internal_reference: 'draft77', display_number: 'draft77', date: NOW, created_at: NOW, artifacts: [],
    customer_readiness: { checked: true, can_issue: true, missing_fields: [] },
  };
  const clickIssue = async (wrapper: VueWrapper) => {
    await wrapper.findAll('button').find((button) => button.text() === 'Выпустить')!.trigger('click');
    await flushPromises();
  };

  it('issues a complete act after the current saved-template check', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValue({ items: [{ ...issueDraft, doc_type: 'act' } as never] });
    const wrapper = await mountWorkspace();
    await clickIssue(wrapper);
    expect(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).toHaveBeenCalledWith(77);
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
  });

  it('requires the printed number from the exact last legacy act and rechecks after a newer act appears', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValue({ items: [{ ...issueDraft, doc_type: 'act', base_customer_contract_id: 91 } as never] });
    const conflict = (id: number, minimum = 0) => ({ status: 409, body: { detail: {
      minimum_previous_number: minimum,
      error_code: 'contract_act_number_confirmation_required',
      previous_act: { id, order_id: 635, number: 'А-2026-086', url: 'https://drive.google.com/open?id=test-source' },
    } } });
    const issue = vi.mocked(ManagerDocumentSystemService.issueManagerManagedDocument)
      .mockRejectedValueOnce(conflict(99)).mockRejectedValueOnce(conflict(100, 22));
    const wrapper = await mountWorkspace();
    await clickIssue(wrapper);
    const panel = wrapper.get('[data-testid="contract-act-number-confirmation"]');
    const input = panel.get<HTMLInputElement>('input');
    expect(input.element.value).toBe('');
    expect(panel.get('a').attributes('href')).toBe('https://drive.google.com/open?id=test-source');
    expect(panel.get('[type="submit"]').attributes('disabled')).toBeDefined();
    await input.setValue('0');
    expect(panel.get('[type="submit"]').text()).toContain('№1');
    await input.setValue('21');
    expect(panel.get('[type="submit"]').text()).toContain('№22');
    await panel.trigger('submit');
    await flushPromises();
    expect(issue).toHaveBeenLastCalledWith(77, false, 21, 99);
    expect(input.element.value).toBe('');
    expect(panel.text()).toContain('Появился более поздний акт');
    await input.setValue('21');
    expect(panel.get('[type="submit"]').attributes('disabled')).toBeDefined();
    expect(panel.text()).toContain('уже использован №22');
    await input.setValue('22');
    await panel.trigger('submit');
    await flushPromises();
    expect(issue).toHaveBeenLastCalledWith(77, false, 22, 100);
    expect(wrapper.find('[data-testid="contract-act-number-confirmation"]').exists()).toBe(false);
  });

  it.each(['contract', 'act'].flatMap((documentType) =>
    ['switch order', 'switch away and back', 'close and reopen'].map((change) => ({ documentType, change }))))
  ('discards $documentType issue readiness after $change without updating the current workspace', async ({ documentType, change }) => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockImplementation(async (orderId) => ({ items: [{ ...issueDraft, doc_type: documentType, order_id: orderId } as never] }));
    const barrier = deferred<typeof missing>();
    vi.mocked(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).mockReturnValue(barrier.promise as never);
    let wrapper = await mountWorkspace();
    await clickIssue(wrapper);
    expect(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).toHaveBeenCalledWith(77);
    if (change === 'close and reopen') {
      wrapper.unmount();
      wrapper = await mountWorkspace();
    } else {
      await wrapper.setProps({ order: { ...baseOrder, id: 43 } });
      await flushPromises();
      if (change === 'switch away and back') {
        await wrapper.setProps({ order: baseOrder });
        await flushPromises();
      }
    }
    const refreshBefore = wrapper.emitted('refresh')?.length || 0;
    // A late missing response must not overwrite even an identically numbered document
    // in the reopened workspace. A late ready response must not authorize its issue.
    barrier.resolve(missing);
    await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
    expect(googleDocumentEditorApi.syncSession).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="native-manual-fields"]').exists()).toBe(false);
    expect(wrapper.emitted('refresh')?.length || 0).toBe(refreshBefore);
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('Не заполнены поля'))).not.toBe(true);
  });

  it.each(['contract', 'act'])('does not issue a ready late %s response after close and reopening another order', async (documentType) => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [{ ...issueDraft, doc_type: documentType } as never] });
    const barrier = deferred<typeof issueDraft.customer_readiness>();
    vi.mocked(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).mockReturnValue(barrier.promise as never);
    const oldWorkspace = await mountWorkspace();
    await clickIssue(oldWorkspace);
    oldWorkspace.unmount();
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [] });
    const newWorkspace = await mountWorkspace(undefined, { ...baseOrder, id: 43 });
    barrier.resolve(issueDraft.customer_readiness);
    await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
    expect(googleDocumentEditorApi.syncSession).not.toHaveBeenCalled();
    expect(newWorkspace.emitted('refresh')).toBeUndefined();
  });

  it('rechecks issue context after awaiting the Google session before syncing or issuing', async () => {
    vi.mocked(googleDocumentEditorApi.getConnectionStatus).mockResolvedValue({ connected: true, provider: 'google_drive' } as never);
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [issueDraft as never] });
    const wrapper = await mountWorkspace();
    const barrier = deferred<never>();
    vi.mocked(googleDocumentEditorApi.getSession).mockReturnValue(barrier.promise);
    await clickIssue(wrapper);
    expect(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).toHaveBeenCalledWith(77);
    await wrapper.setProps({ order: { ...baseOrder, id: 43 } });
    await flushPromises();
    barrier.resolve({ status: 'changed', can_edit: true } as never);
    await flushPromises();
    expect(googleDocumentEditorApi.syncSession).not.toHaveBeenCalled();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
  });

  it('does not refresh a new order when an already submitted issue finishes late', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockImplementation(async (orderId) => ({ items: orderId === 42 ? [issueDraft as never] : [] }));
    const barrier = deferred<never>();
    vi.mocked(ManagerDocumentSystemService.issueManagerManagedDocument).mockReturnValue(new CancelablePromise((resolve, reject) => { void barrier.promise.then(resolve, reject); }));
    const wrapper = await mountWorkspace();
    await clickIssue(wrapper);
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
    await wrapper.setProps({ order: { ...baseOrder, id: 43 } });
    await flushPromises();
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockClear();
    barrier.resolve({} as never);
    await flushPromises();
    expect(ManagerDocumentSystemService.listManagerManagedOrderDocuments).not.toHaveBeenCalled();
    expect(wrapper.emitted('refresh')).toBeUndefined();
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message === 'Документ выпущен')).not.toBe(true);
  });

  it('still issues a ready draft while its order and workspace remain current', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValueOnce({ items: [issueDraft as never] })
      .mockResolvedValue({ items: [{ ...issueDraft, status: 'issued' } as never] });
    const wrapper = await mountWorkspace();
    await clickIssue(wrapper);
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
    expect(wrapper.emitted('refresh')).toHaveLength(1);
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message === 'Документ выпущен')).toBe(true);
  });

  it('does not issue or refresh another order after pending Google synchronization', async () => {
    vi.mocked(googleDocumentEditorApi.getConnectionStatus).mockResolvedValue({ connected: true, provider: 'google_drive' } as never);
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockImplementation(async (orderId) => ({ items: orderId === 42 ? [issueDraft as never] : [] }));
    const wrapper = await mountWorkspace();
    vi.mocked(googleDocumentEditorApi.getSession).mockResolvedValue({ status: 'changed', can_edit: true } as never);
    const barrier = deferred<never>();
    vi.mocked(googleDocumentEditorApi.syncSession).mockReturnValue(barrier.promise);
    await clickIssue(wrapper);
    expect(googleDocumentEditorApi.syncSession).toHaveBeenCalledWith({ kind: 'managed-document', documentId: 77 }, expect.any(Function));
    await wrapper.setProps({ order: { ...baseOrder, id: 43 } });
    await flushPromises();
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockClear();
    barrier.resolve({ session: { status: 'ready', can_edit: true }, newTemplateVersionCreated: false } as never);
    await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
    expect(ManagerDocumentSystemService.listManagerManagedOrderDocuments).not.toHaveBeenCalled();
    expect(wrapper.emitted('refresh')).toBeUndefined();
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('Изменения из Google'))).not.toBe(true);
  });

  it('does not update or refresh a departed workspace after the Google onSynced list read', async () => {
    vi.mocked(googleDocumentEditorApi.getConnectionStatus).mockResolvedValue({ connected: true, provider: 'google_drive' } as never);
    const listBarrier = deferred<{ items: never[] }>();
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValueOnce({ items: [issueDraft as never] })
      .mockReturnValueOnce(listBarrier.promise)
      .mockResolvedValue({ items: [] });
    const wrapper = await mountWorkspace();
    vi.mocked(googleDocumentEditorApi.getSession).mockResolvedValue({ status: 'changed', can_edit: true } as never);
    await clickIssue(wrapper);
    expect(googleDocumentEditorApi.syncSession).toHaveBeenCalledWith({ kind: 'managed-document', documentId: 77 }, expect.any(Function));
    expect(ManagerDocumentSystemService.listManagerManagedOrderDocuments).toHaveBeenCalledTimes(2);
    await wrapper.setProps({ order: { ...baseOrder, id: 43 } });
    await flushPromises();
    const refreshBefore = wrapper.emitted('refresh')?.length || 0;
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockClear();
    listBarrier.resolve({ items: [{ ...issueDraft, customer_readiness: missing } as never] });
    await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
    expect(ManagerDocumentSystemService.listManagerManagedOrderDocuments).not.toHaveBeenCalled();
    expect(wrapper.emitted('refresh')?.length || 0).toBe(refreshBefore);
    expect(wrapper.find('[data-testid="native-manual-fields"]').exists()).toBe(false);
  });

  it.each(['contract', 'act'])('discards ready create preflight after the workspace closes and another order opens for %s', async (documentType) => {
    const barrier = deferred<{ checked: boolean; can_issue: boolean; missing_fields: never[] }>();
    vi.mocked(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).mockReturnValue(barrier.promise as never);
    const oldWorkspace = await mountWorkspace();
    await chooseDocument(oldWorkspace, documentType);
    await oldWorkspace.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    oldWorkspace.unmount();
    const current = await mountWorkspace(undefined, { ...baseOrder, id: 43 });
    barrier.resolve({ checked: true, can_issue: true, missing_fields: [] });
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
    expect(current.emitted('refresh')).toBeUndefined();
    expect(oldWorkspace.emitted('toast')).toBeUndefined();
  });

  it.each(['issue', 'create'])('cancels generated %s transport while its POST token is pending on close', async (action) => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: action === 'issue' ? [issueDraft as never] : [] });
    if (action === 'issue') vi.mocked(ManagerDocumentSystemService.issueManagerManagedDocument).mockRestore();
    else vi.mocked(ManagerDocumentSystemService.createManagerManagedDocumentDraft).mockRestore();
    const tokenBarrier = deferred<string>();
    const previousToken = OpenAPI.TOKEN;
    const token = vi.fn(async (options) => options.method === 'POST' ? tokenBarrier.promise : 'read-token');
    OpenAPI.TOKEN = token;
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{"items":[]}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    try {
      const wrapper = await mountWorkspace();
      if (action === 'issue') await clickIssue(wrapper);
      else {
        await chooseDocument(wrapper);
        await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
        await flushPromises();
      }
      expect(token).toHaveBeenCalledWith(expect.objectContaining({ method: 'POST' }));
      expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0);
      wrapper.unmount();
      tokenBarrier.resolve('late-post-token');
      await flushPromises();
      expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0);
      expect(wrapper.emitted('refresh')).toBeUndefined();
    } finally {
      OpenAPI.TOKEN = previousToken;
    }
  });
});


describe('Participant statement workspace', () => {
  it('creates a statement using the built-in form and manager supplied facts', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerNativeDocumentTemplates).mockResolvedValue({ items: [] });
    const wrapper = await mountWorkspace();
    await wrapper.get('[data-testid="native-document-type-participant_statement"]').trigger('click');
    await flushPromises();
    const button = wrapper.get('[data-testid="create-native-draft"]');
    expect(button.attributes('disabled')).toBeDefined();
    await wrapper.get('[data-testid="participant-statement-procedure"]').setValue('2026-42');
    await wrapper.get('[data-testid="participant-statement-lot"]').setValue('1');
    await wrapper.get('[data-testid="participant-statement-buyer"]').setValue('Заказчик');
    await wrapper.get('[data-testid="participant-statement-text"]').setValue('Подтверждённый текст по требованиям заказчика.');
    expect(button.attributes('disabled')).toBeUndefined();
    await button.trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42,
      expect.objectContaining({ document_type: 'participant_statement', template_id: null,
        participant_statement: { procedure_reference: '2026-42', lot: '1', buyer_name: 'Заказчик',
          declaration_text: 'Подтверждённый текст по требованиям заказчика.' } }));
  });

  it('requires an explicit factual confirmation at issue', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [{
      id: 55, order_id: 42, legal_entity_id: 5, doc_type: 'participant_statement', status: 'draft',
      provider: 'native', display_number: 'doc_statement', internal_reference: 'doc_statement',
      date: NOW, created_at: NOW, document_template_id: 100, template_version_id: 101, artifacts: [],
    }] });
    const wrapper = await mountWorkspace();
    const issue = wrapper.findAll('button').find((button) => button.text() === 'Выпустить')!;
    expect(issue.attributes('disabled')).toBeDefined();
    await wrapper.get('[data-testid="participant-statement-confirm-55"]').setValue(true);
    expect(issue.attributes('disabled')).toBeUndefined();
    await issue.trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(55, true);
  });
});

describe('Standalone sale documents', () => {
  const product = { id: 20, proposal_id: 7, product_id: 3, product_title: 'Кондиционер', quantity: 1, price: 1200 };
  const order = {
    ...baseOrder, customer_contract: null, customer_contract_id: null,
    customer: { ...baseOrder.customer!, type: 'individual' as const, name: 'Покупатель', inn: undefined },
    proposals: [{ ...baseOrder.proposals![0]!, product_lines: [product] }],
  } as ManagerOrderDetailResponse;
  it('creates the first receipt with selected proposal, an optional note and no installation defaults', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerNativeDocumentTemplates).mockResolvedValue({ items: [] });
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-retail_receipt"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="receipt-note"]').setValue('Пуск после отделки');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    const calls = vi.mocked(ManagerDocumentSystemService.createManagerManagedDocumentDraft).mock.calls;
    expect(calls[0]?.[1]).toMatchObject({ document_type: 'retail_receipt', receipt_note: 'Пуск после отделки', proposal_id: 7, template_id: null });
    expect(calls[0]?.[1].consumer_terms).toBeUndefined();
  });
  it('requires choosing equipment from this sale, excludes maintenance-only items and keeps consumer audience', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerNativeDocumentTemplates).mockResolvedValue({ items: [] });
    const unit = { id: 18, customer_id: 11, model: 'Блок', serial: 'AB-123', catalog_product_id: 3, created_at: NOW };
    vi.spyOn(ManagerEquipmentLinksService, 'listManagerOrderEquipmentLinks').mockResolvedValue({ items: [
      { role: 'sale', equipment: unit },
      { role: 'maintenance', equipment: { ...unit, id: 19, serial: 'SERVICE' } },
      { role: 'sale', equipment: { ...unit, id: 20, customer_id: 12, serial: 'OTHER' } },
      { role: 'sale', equipment: { ...unit, id: 21, catalog_product_id: 9, serial: 'ALTERNATIVE' } },
    ] });
    const wrapper = await mountWorkspace(undefined, order);
    await wrapper.get('[data-testid="native-document-type-warranty_certificate"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="native-document-type-retail_receipt"]').exists()).toBe(true);
    const select = wrapper.get('[data-testid="warranty-equipment"]');
    expect(select.findAll('option').map(o => o.text())).toEqual(['Выберите оборудование из продажи', 'Блок · AB-123']);
    const create = wrapper.get('[data-testid="create-native-draft"]');
    expect(create.attributes('disabled')).toBeDefined();
    await select.setValue('18');
    await create.trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42,
      expect.objectContaining({ document_type: 'warranty_certificate', warranty_equipment_id: 18 }));
  });
});
