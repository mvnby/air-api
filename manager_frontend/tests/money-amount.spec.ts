import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import MoneyAmount from '../src/components/money/MoneyAmount.vue';
import OrderMoney from '../src/components/orders/OrderMoney.vue';
import { formatMoney } from '../src/components/orders/order-utils';

describe('Manager money display', () => {
  it.each([
    [0, '0 BYN'], [-12.34, '-12,34 BYN'], [0.01, '0,01 BYN'],
    [123456789.12, '123 456 789,12 BYN'],
  ])('renders finite BYN amount %s with selectable currency text', (value, text) => {
    const wrapper = mount(MoneyAmount, { props: { value } });
    expect(wrapper.text()).toBe(text);
    expect(wrapper.classes()).toContain('whitespace-nowrap');
    expect(wrapper.get('.sr-only').text()).toBe('BYN');
    const svg = wrapper.get('svg');
    expect(svg.attributes('aria-hidden')).toBe('true');
    expect(svg.attributes('viewBox')).toBe('0 0 360.67 446.4');
    expect(svg.get('path').attributes('fill')).toBe('currentColor');
  });

  it.each([undefined, null, NaN, Infinity, -Infinity])('shows missing or nonfinite %s as a dash', value => {
    const wrapper = mount(MoneyAmount, { props: { value, formattedValue: '0.00' } });
    expect(wrapper.text()).toBe('—');
    expect(wrapper.attributes('aria-label')).toBe('Нет данных');
    expect(wrapper.find('svg').exists()).toBe(false);
  });

  it.each(['USD', 'EUR', 'PLN'])('keeps the %s code and field-specific precision', currency => {
    const wrapper = mount(MoneyAmount, { props: { value: 10.2345, formattedValue: '10.2345', currency } });
    expect(wrapper.text()).toBe(`10.2345 ${currency}`);
    expect(wrapper.find('svg').exists()).toBe(false);
  });

  it('preserves a fixed two-decimal formatter without applying another rounding step', () => {
    expect(mount(MoneyAmount, { props: { value: 10, formattedValue: '10.00' } }).text()).toBe('10.00 BYN');
  });

  it.each([0, -10, 0.1, 10.001, 10.239, 123456789.12])('preserves the order formatter for %s', value => {
    expect(mount(OrderMoney, { props: { value } }).text()).toBe(formatMoney(value));
  });
});
