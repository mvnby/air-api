import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import OrderProposalClientPreview from '../src/components/orders/OrderProposalClientPreview.vue';
import type { ProductLine, ServiceLine } from '../src/components/orders/order-editor-types';

describe('OrderProposalClientPreview', () => {
  it('shows customer text and canonical frozen installation lines without internal or invented details', () => {
    const products: ProductLine[] = [{
      product_id: 501,
      product_query: 'Комплект климатической системы',
      client_description: 'Подобранный и согласованный состав: внутренний и наружный блоки.',
      quantity: 1,
      price: 4_200,
      cost: 2_650,
      product_country: 'служебная страна',
      logistics_components: [{ title: 'служебный ProductOption', unit: 'шт.', quantity_per_parent: 1, unit_price: 0 }],
    }];
    const services: ServiceLine[] = [{
      service_id: 9,
      title: 'Устаревшее название свернутого монтажа',
      description: 'Устаревшее описание',
      quantity: 1,
      price: 1_800,
      cost: 900,
      installation_estimate_revision_id: 22,
      installation_projection_mode: 'collapsed',
      installation_display_lines: [{
        title: 'Монтаж с трассой 3 м',
        description: 'Внутренний и наружный блоки, межблочная трасса 3 м; согласованный состав редакции.',
        quantity: 1,
        price: 1_800,
      }],
    }];
    const wrapper = mount(OrderProposalClientPreview, {
      props: {
        productLines: products,
        serviceLines: services,
        title: 'Вариант 2',
        customerName: 'Иван Петров',
        address: 'Минск, ул. Примерная, 7',
      },
    });
    const text = wrapper.text();

    expect(text).toContain('Иван Петров');
    expect(text).toContain('Минск, ул. Примерная, 7');
    expect(text).toContain('Подобранный и согласованный состав: внутренний и наружный блоки.');
    expect(text).toContain('Монтаж с трассой 3 м');
    expect(text).toContain('согласованный состав редакции');
    expect(text).not.toContain('Устаревшее название свернутого монтажа');
    expect(text).not.toContain('служебная страна');
    expect(text).not.toContain('служебный ProductOption');
    expect(text.toLowerCase()).not.toContain('помпа');
    expect(text).not.toContain('Midea');
    expect(wrapper.findAll('button, input, textarea')).toHaveLength(0);
    expect(text.replace(/\s/g, '')).not.toContain('2650');
    expect(text).not.toContain('900 BYN');
  });
});
