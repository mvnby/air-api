import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerService, ManagerContractsService } from '../src/client';
import CustomerReconciliationPanel from '../src/components/customers/CustomerReconciliationPanel.vue';
const report = { customer_id: 42, date_from: '2026-01-01', date_to: '2026-10-03', opening_balance: 0, closing_balance: 30, documents_total: 100, payments_total: 70, documents: [{order_id:1,date:'2026-09-01',amount:100,basis:'Акт № 1',documents:[]}], payments:[{payment_id:1,order_id:1,date:'2026-09-02',amount:70}], ready_for_generation:true, warnings:[] };
let wrapper: VueWrapper;
const button = (text: string) => wrapper.findAll('button').find(item => item.text() === text)!;
beforeEach(() => {
 vi.spyOn(ManagerService,'getManagerCustomerReconciliation').mockResolvedValue(report as never);
 vi.spyOn(ManagerContractsService,'getManagerCustomerContracts').mockResolvedValue({items:[]} as never);
 vi.spyOn(ManagerService,'createManagerCustomerReconciliationDocument').mockResolvedValue({edit_url:'https://docs.google.com/document/d/test'} as never);
 vi.spyOn(ManagerService,'confirmManagerCustomerReconciliationEventRelation').mockResolvedValue({} as never);
});
afterEach(() => { wrapper?.unmount(); vi.restoreAllMocks(); });
const mountPanel = async () => { wrapper = mount(CustomerReconciliationPanel,{props:{customerId:42},global:{stubs:{CustomerLegacyDocumentReview:true}}}); await flushPromises(); };
describe('customer reconciliation', () => {
 it('shows chronological debit/credit movements and blocks creating with changed period', async () => {
  await mountPanel();
  expect(wrapper.findAll('tbody tr').map(row=>row.text())).toEqual([expect.stringContaining('Акт № 1'),expect.stringContaining('Оплата #1')]);
  await wrapper.findAll('input[type="date"]')[0]!.setValue('2025-01-01');
  expect(button('Создать акт сверки').attributes('disabled')).toBeDefined();
  expect(wrapper.text()).toContain('Период или договор изменены');
  await button('Показать').trigger('click'); await flushPromises();
  expect(button('Создать акт сверки').attributes('disabled')).toBeUndefined();
 });
 it('turns a source-change conflict into an actionable original review', async () => {
  vi.mocked(ManagerService.createManagerCustomerReconciliationDocument).mockRejectedValue({status:409,body:{detail:{message:'Оригинал изменился',warnings:[{code:'legacy_source_changed',message:'Оригинал изменился',document_id:9,can_review_legacy:true}]}}});
  await mountPanel(); await button('Создать акт сверки').trigger('click'); await flushPromises();
  expect(button('Создать акт сверки').attributes('disabled')).toBeDefined();
  await button('Проверить оригинал').trigger('click');
  expect(wrapper.findComponent({name:'CustomerLegacyDocumentReview'}).props('documentId')).toBe(9);
 });
 it('requires an explicit explanation before resolving ambiguous delivery documents', async () => {
  vi.mocked(ManagerService.getManagerCustomerReconciliation).mockResolvedValue({...report,ready_for_generation:false,warnings:[{code:'possible_duplicate_delivery_event',message:'Проверьте связь',related_document_ids:[1,2]}]} as never);
  await mountPanel(); await button('Одна поставка или разные?').trigger('click');
  expect(button('Одна поставка').attributes('disabled')).toBeDefined();
  await wrapper.get('input[placeholder^="Что подтверждает"]').setValue('Оригиналы подтверждают одну поставку');
  await button('Одна поставка').trigger('click'); await flushPromises();
  expect(ManagerService.confirmManagerCustomerReconciliationEventRelation).toHaveBeenCalledWith(42,{document_ids:[1,2],relation:'same',reason:'Оригиналы подтверждают одну поставку'});
 });
 it('does not send managed document problems to the legacy review flow', async () => {
  vi.mocked(ManagerService.getManagerCustomerReconciliation).mockResolvedValue({...report,ready_for_generation:false,warnings:[{code:'document_source_unverified',message:'Нет суммы',order_id:7,document_id:2,can_review_legacy:false}]} as never);
  await mountPanel();
  expect(wrapper.text()).not.toContain('Проверить оригинал');
  expect(wrapper.get('a[href="/manager/orders/kanban?orderId=7"]').text()).toBe('Открыть заказ');
 });
});
