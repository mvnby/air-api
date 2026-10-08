import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ManagerDocumentSystemService,
  ManagerDocsService,
  CancelablePromise,
  OpenAPI,
  type ManagerOrderDetailResponse,
} from '../src/client';
import NativeDocumentsWorkspace from '../src/features/documents/components/NativeDocumentsWorkspace.vue';
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
    valid_from: '2026-08-01',
    valid_until: '2027-07-31',
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
  }],
  product_lines: [],
  service_lines: [],
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const wrappers: VueWrapper[] = [];
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

beforeEach(() => {
  confirmDialog.mockReset().mockResolvedValue(true);
  openNativeDocumentPreview.mockReset().mockResolvedValue(undefined);
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

  it.each(['contract', 'act'])('lists only effective server fields and requires an explicit incomplete draft choice for %s', async (documentType) => {
    vi.mocked(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).mockResolvedValue(missing);
    const wrapper = await mountWorkspace();
    await chooseDocument(wrapper, documentType);
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).not.toHaveBeenCalled();
    const warning = wrapper.get('[data-testid="native-customer-readiness-warning"]');
    expect(warning.text()).toContain('Юридический адрес клиента');
    expect(warning.text()).not.toContain('Основание полномочий');
    await wrapper.get('[data-testid="create-incomplete-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.checkManagerManagedDocumentReadiness).toHaveBeenCalledTimes(2);
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42,
      expect.objectContaining({ document_type: documentType, allow_incomplete_customer: true }));
  });

  it.each(['contract', 'act'])('permits a selected template with no missing critical fields even with an incomplete card for %s', async (documentType) => {
    const wrapper = await mountWorkspace();
    await chooseDocument(wrapper, documentType);
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42,
      expect.objectContaining({ allow_incomplete_customer: false }));
    expect(wrapper.find('[data-testid="create-incomplete-native-draft"]').exists()).toBe(false);
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
    expect(wrapper.find('[data-testid="create-incomplete-native-draft"]').exists()).toBe(false);
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
    expect(wrapper.find('[data-testid="create-incomplete-native-draft"]').exists()).toBe(false);
  });

  it.each(['contract', 'act'])('marks the persisted incomplete draft and disables issuance without hiding preview for %s', async (documentType) => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [{
      id: 77, order_id: 42, legal_entity_id: 5, doc_type: documentType, status: 'draft', provider: 'native',
      internal_reference: 'draft77', display_number: 'draft77', date: NOW, created_at: NOW,
      customer_readiness: missing, artifacts: [],
    }] });
    const wrapper = await mountWorkspace();
    expect(wrapper.get('[data-testid="incomplete-native-draft"]').text()).toContain('Не заполнены поля');
    expect(wrapper.get('[data-testid="native-draft-missing-fields"]').text()).toContain('Юридический адрес клиента');
    const issue = wrapper.findAll('button').find((button) => button.text() === 'Выпустить')!;
    expect(issue.attributes('disabled')).toBeDefined();
    const preview = wrapper.findAll('button').find((button) => button.text().includes('Предпросмотр'))!;
    expect(preview.attributes('disabled')).toBeUndefined();
    const fill = wrapper.get('[data-testid="native-draft-missing-fields"]').find('button');
    await fill.trigger('click');
    expect(window.location.pathname).toBe('/manager/customers/profile');
    expect(window.location.search).toContain('customerId=11');
  });

  it.each(['contract', 'act'])('rechecks an old draft with no cached metadata before Google sync or issue for %s', async (documentType) => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments).mockResolvedValue({ items: [{
      id: 77, order_id: 42, legal_entity_id: 5, doc_type: documentType, status: 'draft', provider: 'native',
      internal_reference: 'draft77', display_number: 'draft77', date: NOW, created_at: NOW, artifacts: [],
    }] });
    vi.mocked(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).mockResolvedValue(missing);
    const wrapper = await mountWorkspace();
    const before = vi.mocked(googleDocumentEditorApi.getSession).mock.calls.length;
    await wrapper.findAll('button').find((button) => button.text() === 'Выпустить')!.trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.getManagerManagedDocumentReadiness).toHaveBeenCalledWith(77);
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).not.toHaveBeenCalled();
    expect(googleDocumentEditorApi.syncSession).not.toHaveBeenCalled();
    expect(vi.mocked(googleDocumentEditorApi.getSession).mock.calls.length).toBe(before);
    expect(wrapper.get('[data-testid="native-draft-missing-fields"]').text()).toContain('Юридический адрес клиента');
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
    expect(wrapper.find('[data-testid="incomplete-native-draft"]').exists()).toBe(false);
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
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('официальный номер'))).not.toBe(true);
  });

  it('still issues a ready draft while its order and workspace remain current', async () => {
    vi.mocked(ManagerDocumentSystemService.listManagerManagedOrderDocuments)
      .mockResolvedValueOnce({ items: [issueDraft as never] })
      .mockResolvedValue({ items: [{ ...issueDraft, status: 'issued' } as never] });
    const wrapper = await mountWorkspace();
    await clickIssue(wrapper);
    expect(ManagerDocumentSystemService.issueManagerManagedDocument).toHaveBeenCalledWith(77);
    expect(wrapper.emitted('refresh')).toHaveLength(1);
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('официальный номер'))).toBe(true);
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
    expect(wrapper.find('[data-testid="incomplete-native-draft"]').exists()).toBe(false);
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
