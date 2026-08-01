import { shallowMount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import OrderDocumentsWorkspace from '../src/components/orders/OrderDocumentsWorkspace.vue';

const documentStubs = {
  OrderDrawerSection: {
    name: 'OrderDrawerSection',
    props: ['summary', 'hasError'],
    template: '<section><slot /></section>',
  },
  OrderDocumentsPanel: true,
};

const baseOrder = {
  id: 42,
  status: 'negotiation',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 3_200,
  total_cost: 2_000,
  margin: 1_200,
  is_paid: false,
  customer: {
    id: 11,
    type: 'individual',
    name: 'Анна',
    phone: '+375291112233',
  },
  documents: [],
  product_lines: [],
  service_lines: [],
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const mountedWrappers: VueWrapper[] = [];

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
});

describe('OrderDocumentsWorkspace', () => {
  it('keeps customer messaging links next to the document workspace', () => {
    const wrapper = shallowMount(OrderDocumentsWorkspace, {
      props: {
        order: baseOrder,
        expanded: true,
        productLines: [],
        total: 3_200,
      },
      global: { stubs: documentStubs },
    });
    mountedWrappers.push(wrapper);

    const whatsapp = wrapper.get('a[href^="https://wa.me/"]');
    expect(whatsapp.attributes('href')).toContain('375291112233');
    expect(decodeURIComponent(whatsapp.attributes('href'))).toContain('3 200 BYN');
    expect(wrapper.get('a[href^="viber://"]').attributes('href')).toContain('375291112233');
  });

  it('marks a company without a base document as incomplete', () => {
    const wrapper = shallowMount(OrderDocumentsWorkspace, {
      props: {
        order: {
          ...baseOrder,
          customer: { id: 12, type: 'company', name: 'ООО Климат', inn: '123456789' },
        } as ManagerOrderDetailResponse,
        expanded: true,
        productLines: [],
        total: 0,
      },
      global: { stubs: documentStubs },
    });
    mountedWrappers.push(wrapper);

    const section = wrapper.getComponent({ name: 'OrderDrawerSection' });
    expect(section.props('summary')).toBe('Документов нет');
    expect(section.props('hasError')).toBe(true);
  });
});
