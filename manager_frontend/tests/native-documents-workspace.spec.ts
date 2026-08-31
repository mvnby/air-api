import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ManagerDocumentSystemService,
  type ManagerOrderDetailResponse,
} from '../src/client';
import NativeDocumentsWorkspace from '../src/features/documents/components/NativeDocumentsWorkspace.vue';

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
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({
    items: [{
      id: 5,
      tenant_id: 1,
      slug: 'mvn',
      display_name: 'ООО МВН',
      is_vat_payer: false,
      is_default: true,
      requisites: {
        default_goods_warranty_months: '48',
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
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
});

const mountWorkspace = async () => {
  const wrapper = mount(NativeDocumentsWorkspace, { props: { order: baseOrder } });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
};

describe('NativeDocumentsWorkspace', () => {
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

  it('sends B2C terms only for a consumer order document', async () => {
    const wrapper = await mountWorkspace();

    expect(wrapper.get('[data-testid="native-document-type"]').findAll('optgroup')
      .map((group) => group.attributes('label'))).toEqual(['Для организаций', 'Для физлиц']);

    await wrapper.get('[data-testid="native-document-type"]').setValue('b2c_route_laying_act');
    await flushPromises();

    expect(wrapper.get('[data-testid="consumer-document-terms"]').text())
      .toContain('Параметры закладки трассы');
    expect(wrapper.get('[data-testid="consumer-document-terms"]').text())
      .not.toContain('Гарантия на оборудование');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();

    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        document_type: 'b2c_route_laying_act',
        consumer_terms: expect.objectContaining({ goods_warranty_months: 48 }),
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
