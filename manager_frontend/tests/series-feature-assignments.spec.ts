import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import SeriesFeatureAssignments from '../src/components/brands/SeriesFeatureAssignments.vue';
import type { ManagerFeatureResponse } from '../src/client';

const feature = (id: number): ManagerFeatureResponse => ({
  id,
  slug: `feature-${id}`,
  name: `Фича ${id}`,
  category: { id: 1, name: 'Комфорт', slug: 'comfort', sort_order: 0, is_active: true },
  scope_type: 'universal',
  is_active: true,
  sort_order: id * 10,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

describe('SeriesFeatureAssignments', () => {
  it('selects a catalog feature directly and limits featured choices to three', async () => {
    const wrapper = mount(SeriesFeatureAssignments, {
      props: { features: [feature(1), feature(2), feature(3), feature(4)], modelValue: [] },
    });

    await wrapper.findAll('button').find((button) => button.text() === '')?.trigger('click');
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([[{ feature_id: 1, is_featured: false }]]);

    await wrapper.setProps({ modelValue: [
      { feature_id: 1, is_featured: true },
      { feature_id: 2, is_featured: true },
      { feature_id: 3, is_featured: true },
      { feature_id: 4, is_featured: false },
    ] });
    const starButtons = wrapper.findAll('button').filter((button) => button.attributes('title') === 'Отметить главной');
    expect(starButtons).toHaveLength(1);
    expect(starButtons[0]?.attributes('disabled')).toBeDefined();
  });
});
