import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService, type ManagerOrderDetailResponse } from '../src/client';
import NativeDocumentsWorkspace from '../src/features/documents/components/NativeDocumentsWorkspace.vue';
import { googleDocumentEditorApi } from '../src/features/documents/integrations/google-document-editor-api';

const NOW = '2026-09-09T00:00:00Z';
const wrappers: VueWrapper[] = [];
const defaults = { equipment_brand: 'Midea', equipment_model: 'MSAG-09HRN1', equipment_serial: 'не подставлять', goods_warranty_months: 36, goods_warranty_terms: 'По условиям изготовителя' };
const baseOrder = {
  id: 42, status: 'negotiation', created_at: NOW, total_amount: 3140, total_cost: 2000, margin: 1140, is_paid: false,
  customer: { id: 11, type: 'individual', name: 'Покупатель' }, documents: [], product_lines: [], service_lines: [],
  proposals: [{ id: 7, order_id: 42, name: 'Основное', is_selected: true, is_archived: false, product_lines: [{ line_total: 3140 }] }],
  needs_attention: false, awaiting_measurement: false, client_thinking: false, ready_for_execution: false,
} as ManagerOrderDetailResponse;
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve };
};

beforeEach(() => {
  vi.spyOn(googleDocumentEditorApi, 'getConnectionStatus').mockResolvedValue({ connected: false, provider: 'google_drive', account_label: null, managed_folder_url: null, connected_at: null, last_verified_at: null, last_error_code: null });
  vi.spyOn(googleDocumentEditorApi, 'getSession').mockResolvedValue(null);
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({ items: [{ id: 5, tenant_id: 1, slug: 'mvn', display_name: 'ООО МВН', is_default: true, status: 'active', requisites: { city: 'Витебск', default_goods_warranty_months: '48', default_work_warranty_months: '12', offer_url: 'https://mvn.by/offer', offer_version: '1.0', offer_published_on: '04.06.2026' }, created_at: NOW, updated_at: NOW }] });
  vi.spyOn(ManagerDocumentSystemService, 'getManagerDocumentPdfRuntime').mockResolvedValue({ available: true, provider: 'gotenberg', detail: 'healthy' });
  vi.spyOn(ManagerDocumentSystemService, 'listManagerManagedOrderDocuments').mockResolvedValue({ items: [] });
  vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeDocumentTemplates').mockImplementation(async (_id, docType) => ({ items: [{ id: 100, tenant_id: 1, legal_entity_id: 5, name: 'Шаблон', doc_type: docType || 'contract', is_default: true, is_active: true, sort_order: 0, created_at: NOW }] }));
  vi.spyOn(ManagerDocumentSystemService, 'listManagerNativeTemplateVersions').mockResolvedValue({ items: [{ id: 101, template_id: 100, version: 1, status: 'active', renderer: 'docx', checksum_sha256: 'a'.repeat(64), placeholder_schema: {}, created_at: NOW }] });
  vi.spyOn(ManagerDocumentSystemService, 'getManagerConsumerEquipmentDefaults').mockResolvedValue(defaults);
  vi.spyOn(ManagerDocumentSystemService, 'createManagerManagedDocumentDraft').mockResolvedValue({} as never);
});
afterEach(() => { for (const wrapper of wrappers.splice(0)) wrapper.unmount(); vi.restoreAllMocks(); });
const mountConsumerWorkspace = async () => {
  const wrapper = mount(NativeDocumentsWorkspace, { props: { order: baseOrder } });
  wrappers.push(wrapper);
  await flushPromises();
  await wrapper.get('[data-testid="native-audience-consumer"]').trigger('click');
  await flushPromises();
  return wrapper;
};

describe('consumer installation documents', () => {
  it.each(['b2c_customer_equipment_installation_act', 'b2c_maintenance_repair_act', 'b2c_route_laying_act'])('clears sale stages when switching to %s', async (documentType) => {
    const wrapper = await mountConsumerWorkspace();
    await wrapper.get('[data-testid="installation-two-stages-toggle"]').trigger('click');
    await wrapper.get('[data-testid="installation-first-stage-amount"]').setValue('3000');
    await wrapper.get('[data-testid="native-document-type"]').setValue(documentType);
    await flushPromises();
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42, expect.objectContaining({ document_type: documentType, consumer_terms: expect.objectContaining({ installation_two_stages: false, installation_first_stage_amount: null }) }));
  });

  it('serializes exact two-stage amounts and clears them with the direct toggle', async () => {
    const wrapper = await mountConsumerWorkspace();
    await wrapper.get('[data-testid="installation-two-stages-toggle"]').trigger('click');
    await wrapper.get('[data-testid="installation-first-stage-amount"]').setValue('3000,00');
    expect(wrapper.get<HTMLInputElement>('[data-testid="installation-second-stage-amount"]').element.value).toBe('140,00 BYN');
    await wrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenCalledWith(42, expect.objectContaining({ consumer_terms: expect.objectContaining({ installation_two_stages: true, installation_first_stage_amount: '3000.00' }) }));
    const clearWrapper = await mountConsumerWorkspace();
    await clearWrapper.get('[data-testid="installation-two-stages-toggle"]').trigger('click');
    await clearWrapper.get('[data-testid="installation-first-stage-amount"]').setValue('3000');
    await clearWrapper.get('[data-testid="installation-two-stages-toggle"]').trigger('click');
    await clearWrapper.get('[data-testid="create-native-draft"]').trigger('click');
    await flushPromises();
    expect(ManagerDocumentSystemService.createManagerManagedDocumentDraft).toHaveBeenLastCalledWith(42, expect.objectContaining({ consumer_terms: expect.objectContaining({ installation_two_stages: false, installation_first_stage_amount: null }) }));
  });

  it('preserves manual equipment through a date-based defaults refresh', async () => {
    const wrapper = await mountConsumerWorkspace();
    await wrapper.get('[data-testid="consumer-equipment-brand"]').setValue('Ручной бренд');
    await wrapper.get('[data-testid="native-document-issue-date"]').setValue('2026-10-01');
    await flushPromises();
    expect(ManagerDocumentSystemService.getManagerConsumerEquipmentDefaults).toHaveBeenLastCalledWith(42, 7, '2026-10-01');
    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-equipment-brand"]').element.value).toBe('Ручной бренд');
  });

  it('discards stale defaults and does not carry sold equipment into a customer-equipment act', async () => {
    const first = deferred<typeof defaults>();
    const second = deferred<typeof defaults>();
    vi.mocked(ManagerDocumentSystemService.getManagerConsumerEquipmentDefaults).mockReset().mockReturnValueOnce(first.promise as never).mockReturnValueOnce(second.promise as never);
    const wrapper = await mountConsumerWorkspace();
    await wrapper.get('[data-testid="native-document-issue-date"]').setValue('2026-10-01');
    second.resolve({ ...defaults, equipment_brand: 'Новая модель' });
    await flushPromises();
    first.resolve({ ...defaults, equipment_brand: 'Старая модель' });
    await flushPromises();
    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-equipment-brand"]').element.value).toBe('Новая модель');
    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-equipment-serial"]').element.value).toBe('');
    await wrapper.get('[data-testid="native-document-type"]').setValue('b2c_customer_equipment_installation_act');
    await flushPromises();
    expect(wrapper.get<HTMLInputElement>('[data-testid="consumer-equipment-brand"]').element.value).toBe('');
  });
});
