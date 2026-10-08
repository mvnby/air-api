import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderWorkspaceContext from '../src/components/orders/OrderWorkspaceContext.vue';
const fullName = 'Учреждение здравоохранения «Витебский областной клинический диагностический центр»';
const make = () => mount(OrderWorkspaceContext, { props: { customerName: fullName, address: 'Витебск, ул. Доватора, 2', total: 600, paid: 100, balance: 500 }, slots: { customer: '<input aria-label="Данные клиента" />', object: '<input aria-label="Адрес объекта" />' } });
describe('order context accordion layout', () => {
  it('keeps the full legal name and emits local expansion actions', async () => {
    const w = make(); const client = w.get('[data-order-usage="context-customer"]');
    expect(client.text()).toContain(fullName); expect(client.attributes('aria-expanded')).toBe('false');
    await client.trigger('click'); expect(w.emitted('customer')).toHaveLength(1);
    await w.get('[data-order-usage="context-object"]').trigger('click'); expect(w.emitted('object')).toHaveLength(1);
  });
  it('places each editor within the same section as its header', async () => {
    const w = make(); await w.setProps({ expanded: 'customer' });
    const section = w.get('[data-order-usage="context-customer"]').element.parentElement!;
    expect(section.querySelector('[aria-label="Данные клиента"]')).not.toBe(null);
    expect(w.get('[data-order-usage="context-customer"]').attributes('aria-expanded')).toBe('true');
    expect(w.get('#order-context-object-editor').attributes('style')).toContain('display: none');
  });
  it('keeps money precision, unknown values and disabled context actions', async () => {
    const w = make();
    await w.setProps({ paid: -0.25, total: 1234567.89, balance: 0, disabled: true });
    expect(w.text()).toContain('-0,25 BYN из 1\u00a0234\u00a0567,89 BYN');
    expect(w.text()).toContain('Оплачено');
    expect(w.get('[data-order-usage="context-customer"]').attributes('disabled')).toBeDefined();
    await w.setProps({ paid: NaN });
    expect(w.get('[data-order-usage="context-payments"]').text()).toContain('—');
    w.unmount();
  });
  it('preserves payment navigation and totals', async () => {
    const w = make(); await w.get('[data-order-usage="context-payments"]').trigger('click');
    expect(w.emitted('payments')).toHaveLength(1); expect(w.text()).toContain('100 BYN из 600 BYN'); expect(w.text()).toContain('Остаток 500 BYN');
  });
});
