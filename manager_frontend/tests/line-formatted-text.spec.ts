import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import LineFormattedText from '../src/components/orders/LineFormattedText.vue';
import { parseLineText } from '../src/components/orders/line-formatted-text';

describe('restricted line formatting', () => {
  it('renders bold, italic and newlines, with HTML and links as literal text', () => {
    const text = '**Работы:**\r\n*Осмотр* <img src=x onerror=alert(1)> [ссылка](url) * без пары';
    const wrapper = mount(LineFormattedText, { props: { text } });
    expect(wrapper.find('strong').text()).toBe('Работы:');
    expect(wrapper.find('em').text()).toBe('Осмотр');
    expect(wrapper.element.textContent).toBe('Работы:\r\nОсмотр <img src=x onerror=alert(1)> [ссылка](url) * без пары');
    expect(wrapper.findAll('img, a, script')).toHaveLength(0);
    expect(wrapper.classes()).toContain('whitespace-pre-wrap');
    expect(wrapper.classes()).toContain('font-normal');
    expect(mount(LineFormattedText, { props: { text: 'Обычное название' } }).classes()).not.toContain('font-normal');
  });
  it('supports combined emphasis while leaving arithmetic stars unchanged', () => {
    expect(parseLineText('***Важно***')).toEqual([{ text: 'Важно', bold: true, italic: true }]);
    expect(parseLineText('**Работы *важно***')).toEqual([{ text: 'Работы ', bold: true, italic: false }, { text: 'важно', bold: true, italic: true }]);
    expect(parseLineText('*'.repeat(10_000))).toEqual([{ text: '*'.repeat(10_000), bold: false, italic: false }]);
    expect(parseLineText('**Без пары*')).toEqual([{ text: '**Без пары*', bold: false, italic: false }]);
    expect(parseLineText('Цена * 2 * 3')).toEqual([{ text: 'Цена * 2 * 3', bold: false, italic: false }]);
  });
});
