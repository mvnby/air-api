import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService, type DocumentLegalEntityItem } from '../src/client';
import { api } from '../src/api';
import DocumentLegalEntitiesPanel from '../src/features/documents/settings/DocumentLegalEntitiesPanel.vue';
import NativeTemplateLibrary from '../src/features/documents/settings/NativeTemplateLibrary.vue';
import { googleDocumentEditorApi } from '../src/features/documents/integrations/google-document-editor-api';


const NOW = '2026-08-27T00:00:00Z';
const wrappers: VueWrapper[] = [];

const entity = (overrides: Partial<DocumentLegalEntityItem> = {}): DocumentLegalEntityItem => ({
  id: 7,
  tenant_id: 1,
  slug: 'seller',
  display_name: 'ООО Продавец',
  legal_name: null,
  unp: null,
  entity_type: 'organization',
  is_vat_payer: false,
  is_default: true,
  requisites: {},
  status: 'active',
  created_at: NOW,
  updated_at: NOW,
  ...overrides,
});

const mountPanel = (item: DocumentLegalEntityItem = entity()) => {
  const wrapper = mount(DocumentLegalEntitiesPanel, {
    props: {
      items: [item],
      selectedId: item.id,
      loading: false,
      saving: false,
    },
  });
  wrappers.push(wrapper);
  return wrapper;
};

beforeEach(() => {
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
    id: 'template-session-10',
    status: 'ready',
    edit_url: 'https://docs.google.com/document/d/template-10/edit',
    can_edit: true,
    base_checksum_sha256: 'a'.repeat(64),
    remote_revision: 'revision-1',
    modified_at: NOW,
    last_synced_at: NOW,
    detail: null,
  });
  vi.spyOn(googleDocumentEditorApi, 'syncSession').mockResolvedValue({
    session: {
      id: 'template-session-10',
      status: 'ready',
      edit_url: 'https://docs.google.com/document/d/template-10/edit',
      can_edit: true,
      base_checksum_sha256: 'b'.repeat(64),
      remote_revision: 'revision-2',
      modified_at: NOW,
      last_synced_at: NOW,
      detail: null,
    },
    newTemplateVersionCreated: true,
  });
  vi.spyOn(api, 'getCompanyByUnp').mockResolvedValue({
    row: {
      vnaimp: 'Индивидуальный предприниматель Иванов Иван Иванович',
      vpadres: '210000, г. Витебск, ул. Тестовая, 1',
    },
  });
  vi.spyOn(api, 'getBankBySearch').mockResolvedValue({
    name: 'ОАО Тест Банк',
    address: 'г. Минск',
    bic: 'TESTBY2X',
  });
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
});

describe('DocumentLegalEntitiesPanel', () => {
  it('persists the direct Organization / IP switch', async () => {
    const wrapper = mountPanel();
    const typeButtons = wrapper.get('[data-testid="seller-entity-type"]').findAll('button');

    expect(typeButtons.map((button) => button.text())).toEqual(['Организация', 'ИП']);
    await typeButtons[1]!.trigger('click');
    expect(wrapper.text()).toContain('Адрес регистрации');
    expect(wrapper.text()).toContain('ФИО предпринимателя');
    await wrapper.get('form.grid').trigger('submit');

    expect(wrapper.emitted('update')?.[0]).toEqual([
      7,
      expect.objectContaining({ entity_type: 'individual_entrepreneur' }),
    ]);
  });

  it('normalizes UNP and IBAN and fills blank requisites from shared lookups', async () => {
    const wrapper = mountPanel();

    await wrapper.get('[data-testid="seller-unp"]').setValue('123 456 789');
    await wrapper.get('[data-testid="seller-unp"]').trigger('blur');
    await wrapper.get('[data-testid="seller-iban"]').setValue('by12 test 0000 0000');
    await wrapper.get('[data-testid="seller-iban"]').trigger('blur');
    await flushPromises();

    expect(api.getCompanyByUnp).toHaveBeenCalledWith('123456789');
    expect(api.getBankBySearch).toHaveBeenCalledWith('BY12TEST00000000');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-legal-name"]').element.value)
      .toBe('Индивидуальный предприниматель Иванов Иван Иванович');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-legal-address"]').element.value)
      .toBe('210000, г. Витебск, ул. Тестовая, 1');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-bank-name"]').element.value)
      .toBe('ОАО Тест Банк, г. Минск');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-bic"]').element.value)
      .toBe('TESTBY2X');
    expect(wrapper.text()).toContain('Наименование и адрес найдены в ЕГР');
    expect(wrapper.text()).toContain('Банк и BIC определены по IBAN');
  });

  it('does not overwrite manually entered legal and bank details', async () => {
    const wrapper = mountPanel(entity({
      legal_name: 'Уточнённое наименование',
      requisites: {
        legal_address: 'Уточнённый адрес',
        bank_name: 'Уточнённый банк',
        bic: 'MANUALBIC',
      },
    }));

    await wrapper.get('[data-testid="seller-unp"]').setValue('123456789');
    await wrapper.get('[data-testid="seller-unp"]').trigger('blur');
    await wrapper.get('[data-testid="seller-iban"]').setValue('BY12TEST00000000');
    await wrapper.get('[data-testid="seller-iban"]').trigger('blur');
    await flushPromises();

    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-legal-name"]').element.value)
      .toBe('Уточнённое наименование');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-legal-address"]').element.value)
      .toBe('Уточнённый адрес');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-bank-name"]').element.value)
      .toBe('Уточнённый банк');
    expect(wrapper.get<HTMLInputElement>('[data-testid="seller-bic"]').element.value)
      .toBe('MANUALBIC');
  });

  it('saves consumer offer policy without resubmitting unrelated requisites', async () => {
    const wrapper = mountPanel(entity({
      requisites: {
        phone: '+375291234567',
        offer_url: 'https://old.example/offer',
      },
    }));

    await wrapper.get('[data-testid="consumer-offer-url"]').setValue('https://mvn.by/offer');
    await wrapper.get('[data-testid="default-goods-warranty-months"]').setValue('48');
    await wrapper.get('form.grid').trigger('submit');

    expect(wrapper.emitted('update')?.[0]?.[1]).toEqual(expect.objectContaining({
      requisites: expect.objectContaining({
        offer_url: 'https://mvn.by/offer',
        default_goods_warranty_months: 48,
      }),
    }));
    expect(wrapper.emitted('update')?.[0]?.[1].requisites).not.toHaveProperty('phone');
  });
});

describe('NativeTemplateLibrary', () => {
  it('corrects an existing template use case without creating a duplicate', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeDocumentTemplates').mockResolvedValue({
      items: [{
        id: 10,
        tenant_id: 1,
        legal_entity_id: 5,
        name: 'Договор ремонта',
        doc_type: 'contract',
        description: 'Старая карточка',
        contract_scenario: 'repair',
        business_role: null,
        is_default: false,
        is_active: true,
        sort_order: 0,
        created_at: NOW,
      }],
    });
    vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeTemplateVersions').mockResolvedValue({ items: [] });
    vi.spyOn(ManagerDocumentSystemService, 'getManagerNativePlaceholderCatalog').mockResolvedValue({
      document_type: 'contract',
      fields: [],
      conditions: [],
      tables: [],
    });
    vi.spyOn(ManagerDocumentSystemService, 'createManagerNativeDocumentTemplate').mockResolvedValue({} as never);
    vi.spyOn(ManagerDocumentSystemService, 'updateManagerNativeDocumentTemplate').mockResolvedValue({} as never);
    const wrapper = mount(NativeTemplateLibrary, { props: { legalEntityId: 5 } });
    wrappers.push(wrapper);
    await flushPromises();

    await wrapper.get('[data-testid="native-template-metadata-name"]').setValue('Договор услуг');
    await wrapper.get('[data-testid="native-template-metadata-description"]').setValue('Исправленная карточка');
    await wrapper.get('[data-testid="native-template-metadata-contract-scenario"]').setValue('services');
    await wrapper.get('[data-testid="native-template-metadata"]').trigger('submit');
    await flushPromises();

    expect(ManagerDocumentSystemService.updateManagerNativeDocumentTemplate).toHaveBeenCalledWith(10, {
      legal_entity_id: 5,
      name: 'Договор услуг',
      description: 'Исправленная карточка',
      contract_scenario: 'services',
      business_role: null,
    });
    expect(ManagerDocumentSystemService.createManagerNativeDocumentTemplate).not.toHaveBeenCalled();
  });

  it('opens and imports an online template edit only when Google Drive is connected', async () => {
    vi.mocked(googleDocumentEditorApi.getConnectionStatus).mockResolvedValue({
      connected: true,
      provider: 'google_drive',
      account_label: 'docs@example.com',
      managed_folder_url: 'https://drive.google.com/drive/folders/crm',
      connected_at: NOW,
      last_verified_at: NOW,
      last_error_code: null,
    });
    vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeDocumentTemplates').mockResolvedValue({
      items: [{
        id: 10,
        tenant_id: 1,
        legal_entity_id: 5,
        name: 'Договор ремонта',
        doc_type: 'contract',
        is_default: true,
        is_active: true,
        sort_order: 0,
        created_at: NOW,
      }],
    });
    vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeTemplateVersions').mockResolvedValue({
      items: [{
        id: 20,
        template_id: 10,
        version: 1,
        status: 'active',
        renderer: 'docx',
        source_filename: 'contract.docx',
        checksum_sha256: 'a'.repeat(64),
        placeholder_schema: {},
        created_at: NOW,
      }],
    });
    vi.spyOn(ManagerDocumentSystemService, 'getManagerNativePlaceholderCatalog').mockResolvedValue({
      document_type: 'contract',
      fields: [],
      conditions: [],
      tables: [],
    });
    const replace = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue({ opener: null, location: { replace }, close: vi.fn() } as never);
    const wrapper = mount(NativeTemplateLibrary, { props: { legalEntityId: 5 } });
    wrappers.push(wrapper);
    await flushPromises();

    expect(wrapper.get('[data-testid="template-google-connected"]').text()).toContain('docs@example.com');
    const edit = wrapper.findAll('button').find((button) => button.text().includes('Редактировать в Google Docs'));
    expect(edit).toBeDefined();
    await edit!.trigger('click');
    await flushPromises();

    expect(googleDocumentEditorApi.createSession).toHaveBeenCalledWith({
      kind: 'template-version',
      templateId: 10,
      versionId: 20,
      legalEntityId: 5,
    });
    expect(replace).toHaveBeenCalledWith('https://docs.google.com/document/d/template-10/edit');

    vi.mocked(googleDocumentEditorApi.getSession).mockResolvedValue({
      id: 'template-session-10',
      status: 'ready',
      edit_url: 'https://docs.google.com/document/d/template-10/edit',
      can_edit: true,
      base_checksum_sha256: 'a'.repeat(64),
      remote_revision: 'revision-1',
      modified_at: NOW,
      last_synced_at: NOW,
      detail: null,
    });

    const sync = wrapper.findAll('button').find((button) => button.text().includes('Забрать изменения'));
    await sync!.trigger('click');
    await flushPromises();
    expect(googleDocumentEditorApi.syncSession).toHaveBeenCalled();
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('новая версия шаблона'))).toBe(true);

    vi.mocked(googleDocumentEditorApi.syncSession).mockResolvedValueOnce({
      session: {
        id: 'template-session-10',
        status: 'ready',
        edit_url: 'https://docs.google.com/document/d/template-10/edit',
        can_edit: true,
        base_checksum_sha256: 'b'.repeat(64),
        remote_revision: 'revision-2',
        modified_at: NOW,
        last_synced_at: NOW,
        detail: null,
      },
      newTemplateVersionCreated: false,
    });
    await wrapper.findAll('button').find((button) => button.text().includes('Забрать изменения'))!.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('toast')?.some(([payload]) => payload.message.includes('новых изменений нет'))).toBe(true);

    const statusCallsBeforeFocus = vi.mocked(googleDocumentEditorApi.getConnectionStatus).mock.calls.length;
    const sessionCallsBeforeFocus = vi.mocked(googleDocumentEditorApi.getSession).mock.calls.length;
    window.dispatchEvent(new Event('focus'));
    await flushPromises();
    expect(googleDocumentEditorApi.getConnectionStatus).toHaveBeenCalledTimes(statusCallsBeforeFocus + 1);
    expect(vi.mocked(googleDocumentEditorApi.getSession).mock.calls.length).toBeGreaterThan(sessionCallsBeforeFocus);

    wrapper.unmount();
    const statusCallsAfterUnmount = vi.mocked(googleDocumentEditorApi.getConnectionStatus).mock.calls.length;
    window.dispatchEvent(new Event('focus'));
    await flushPromises();
    expect(googleDocumentEditorApi.getConnectionStatus).toHaveBeenCalledTimes(statusCallsAfterUnmount);
  });
});
