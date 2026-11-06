import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import type { WebsiteInterests as Interests } from '../src/client';
import WebsiteInterests from '../src/components/WebsiteInterests.vue';

const interests: Interests = { version: 1, consent: true, items: [
  { kind: 'product', page_path: '/product/daikin', title: '<script>Daikin FTX</script>', active_seconds: 123, product_id: 999, topics: ['Тихая работа', 'Тепловой насос'] },
  { kind: 'article', page_path: '/articles/quiet', title: 'Как выбрать кондиционер', active_seconds: 30 },
] };

describe('Website interests as internal facts', () => {
  it('shows public titles, paths, model, topics and approximate time as escaped text', () => {
    const wrapper = mount(WebsiteInterests, { props: { interests } });
    expect(wrapper.get('[data-testid="website-interests"]').text()).toContain('Интересы на сайте');
    expect(wrapper.findAll('[data-testid="website-interest-item"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('<script>Daikin FTX</script>');
    expect(wrapper.find('script').exists()).toBe(false);
    expect(wrapper.text()).toContain('Товар #999');
    expect(wrapper.text()).toContain('/product/daikin');
    expect(wrapper.text()).toContain('Темы: Тихая работа, Тепловой насос');
    expect(wrapper.text()).toContain('≈ 2 мин');
    expect(wrapper.text()).toContain('< 1 мин');
    expect(wrapper.findAll('button, input, a')).toHaveLength(0);
    wrapper.unmount();
  });

  it.each([undefined, null, { ...interests, consent: false }, { ...interests, items: [] }])('hides the block when no consented summary is available: %s', (summary) => {
    const wrapper = mount(WebsiteInterests, { props: { interests: summary } });
    expect(wrapper.find('[data-testid="website-interests"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
