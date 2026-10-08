import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerService, ManagerContractsService } from '../src/client';
import CustomerLegacyDocumentReview from '../src/components/customers/CustomerLegacyDocumentReview.vue';
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

describe('reconciliation money presentation', () => {
 it('keeps precision, missing amounts, debt labels and debit/credit blanks', async () => {
  vi.mocked(ManagerService.getManagerCustomerReconciliation).mockResolvedValue({...report, opening_balance: -1234567.89, documents_total: 0, payments_total: undefined, closing_balance: -12.34} as never);
  await mountPanel();
  const totals = wrapper.findAll('.balance-grid strong');
  expect(totals.map(item => item.text())).toEqual(['-1\u00a0234\u00a0567,89 BYN', '0,00 BYN', '—', '12,34 BYN']);
  expect(totals[2]!.get('[aria-label="Нет данных"]').exists()).toBe(true);
  expect(wrapper.text()).toContain('Переплата / аванс клиента');
  expect(wrapper.findAll('tbody tr')[0]!.findAll('td').slice(2).map(item => item.text())).toEqual(['100,00 BYN', '—', '-1\u00a0234\u00a0467,89 BYN']);
  expect(wrapper.findAll('tbody tr')[1]!.findAll('td')[2]!.text()).toBe('—');
  expect(totals[0]!.get('svg').attributes('aria-hidden')).toBe('true');
 });
 it('does not turn a missing closing balance into zero', async () => {
  vi.mocked(ManagerService.getManagerCustomerReconciliation).mockResolvedValue({...report, closing_balance: undefined} as never);
  await mountPanel();
  expect(wrapper.findAll('.balance-grid strong')[3]!.text()).toBe('—');
 });
 it('retains the original-review amount input and confirmation payload', async () => {
  vi.spyOn(ManagerService, 'reviewManagerCustomerReconciliationLegacyDocument').mockResolvedValue({proposed_number:'A-1', proposed_date:'2026-10-01', proposed_amount:1234.56, proposed_contract_id:null, extracted_text:'Акт A-1 на сумму 1234.56', source_hash:'source-hash'} as never);
  vi.spyOn(ManagerService, 'confirmManagerCustomerReconciliationLegacyDocument').mockResolvedValue({} as never);
  wrapper = mount(CustomerLegacyDocumentReview, {props:{customerId:42, documentId:9, contracts:[]}});
  await flushPromises();
  const input = wrapper.get('input[type="number"]');
  expect(input.element.closest('label')!.textContent).toContain('Сумма, BYN');
  expect(input.attributes()).toMatchObject({min:'0.01',step:'0.01',required:''});
  expect((input.element as HTMLInputElement).value).toBe('1234.56');
  await input.setValue('12.34');
  await wrapper.get('textarea').setValue('Акт A-1 на сумму 12.34');
  await wrapper.get('form').trigger('submit');
  await flushPromises();
  expect(ManagerService.confirmManagerCustomerReconciliationLegacyDocument).toHaveBeenCalledWith(42,9,{number:'A-1',date:'2026-10-01',amount:12.34,contract_id:null,evidence_excerpt:'Акт A-1 на сумму 12.34',source_hash:'source-hash'});
  expect(wrapper.emitted('confirmed')).toHaveLength(1);
 });
});
