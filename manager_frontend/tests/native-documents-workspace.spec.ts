import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ManagerDocumentSystemService,
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
  vi.spyOn(ManagerDocumentSystemService, 'createManagerManagedDocumentDraft').mockResolvedValue({} as never);
  vi.spyOn(ManagerDocumentSystemService, 'issueManagerManagedDocument').mockResolvedValue({} as never);
  vi.spyOn(ManagerDocumentSystemService, 'deleteManagerManagedDocumentDraft').mockResolvedValue(undefined as never);
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
  managerSession.auth.value = null;
});

const mountWorkspace = async () => {
  const wrapper = mount(NativeDocumentsWorkspace, { props: { order: baseOrder } });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};

describe('NativeDocumentsWorkspace', () => {
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

  it('uses the active customer contract as the default basis for an act', async () => {
    const wrapper = await mountWorkspace();

    await wrapper.get('[data-testid="native-document-type"]').setValue('act');
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

    await wrapper.get('[data-testid="native-document-type"]').setValue('act');
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

    await wrapper.get('[data-testid="native-document-type"]').setValue('invoice');
    await flushPromises();

    const toggle = wrapper.get('[data-testid="invoice-role-toggle"]');
    expect(toggle.findAll('button').map((button) => button.text())).toEqual([
      'Документ для оплаты',
      'Счёт-оферта',
    ]);
    await toggle.findAll('button')[1]!.trigger('click');
    expect(toggle.text()).toContain('Счёт-оферта');
  });

  it('requires one of seven direct contract scenarios before creating a B2B contract', async () => {
    const wrapper = await mountWorkspace();
    const create = wrapper.get('[data-testid="create-native-draft"]');

    expect(create.attributes('disabled')).toBeDefined();
    expect(create.attributes('title')).toContain('Выберите сценарий договора');
    expect(wrapper.findAll('button[data-testid^="contract-scenario-"]')).toHaveLength(7);

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

  it('sends B2C terms only for a consumer order document', async () => {
    const wrapper = await mountWorkspace();

    expect(wrapper.get('[data-testid="native-document-type"]').findAll('option')
      .map((option) => option.attributes('value'))).not.toContain('b2c_route_laying_act');
    await wrapper.get('[data-testid="native-audience-consumer"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="native-document-type"]').findAll('option')
      .map((option) => option.attributes('value'))).toContain('b2c_route_laying_act');

    await wrapper.get('[data-testid="native-document-type"]').setValue('b2c_route_laying_act');
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
          goods_warranty_months: 48,
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
    await wrapper.get('[data-testid="native-document-type"]').setValue('b2c_supply_installation_act');
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

    await wrapper.get('[data-testid="native-document-type"]').setValue('act');
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
