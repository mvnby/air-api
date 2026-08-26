import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listTenantCatalog: vi.fn(),
}));

vi.mock('../src/client', () => ({
  OpenAPI: {},
  ManagerTenantCatalogService: {
    listManagerTenantCatalogProducts: mocks.listTenantCatalog,
  },
}));

import {
  MANAGER_CAPABILITY,
  isManagerPathAllowed,
} from '../src/manager-capabilities';
import { coreNavItems, navSections } from '../src/manager-navigation';
import TenantCatalogView from '../src/views/TenantCatalogView.vue';
import { sanitizeEquipmentComponentPayload } from '../src/components/equipment/equipment-component-permissions';
import { api } from '../src/api';
import { managerSession } from '../src/services/manager-session';

const tenantManagerAuth = {
  capabilities: [
    MANAGER_CAPABILITY.crmManage,
    MANAGER_CAPABILITY.catalogMasterRead,
    MANAGER_CAPABILITY.storefrontOffersRead,
    MANAGER_CAPABILITY.storefrontCollectionsManage,
  ],
};

const allowedCatalogProduct = {
  id: 1,
  title: 'Allowed Model',
  slug: 'allowed-model',
  brand_title: 'Safe Brand',
  series_title: 'Safe Series',
  main_image: null,
  product_kind: 'split',
  is_inverter: true,
  power_cooling: 2.5,
  offer_id: 10,
  offer_status: 'active',
  offer_is_published: true,
  effective_price: 1750,
  allowed: true,
};

describe('tenant manager capabilities', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listTenantCatalog.mockResolvedValue({
      items: [
        allowedCatalogProduct,
        {
          id: 2,
          title: 'Blocked Model',
          slug: 'blocked-model',
          brand_title: null,
          series_title: null,
          main_image: null,
          product_kind: 'split',
          is_inverter: false,
          power_cooling: null,
          offer_id: null,
          offer_status: null,
          offer_is_published: null,
          effective_price: null,
          allowed: false,
        },
      ],
      meta: { page: 1, limit: 100, total: 2, pages: 1 },
    });
    managerSession.auth.value = tenantManagerAuth as any;
  });

  it('allows CRM, the read-only catalog and exact storefront collections', () => {
    for (const path of [
      '/manager',
      '/manager/leads',
      '/manager/orders/kanban',
      '/manager/calendar',
      '/manager/customers',
      '/manager/equipment',
      '/manager/products',
      '/manager/product-collections',
    ]) {
      expect(isManagerPathAllowed(tenantManagerAuth, path), path).toBe(true);
    }
    for (const path of [
      '/manager/products/1',
      '/manager/brands',
      '/manager/suppliers',
      '/manager/supply',
      '/manager/media',
      '/manager/staff',
      '/manager/settings',
    ]) {
      expect(isManagerPathAllowed(tenantManagerAuth, path), path).toBe(false);
    }

    const visibleLabels = [...coreNavItems, ...navSections.flatMap(section => section.items)]
      .filter(item => !item.requiredCapability || tenantManagerAuth.capabilities.includes(item.requiredCapability))
      .map(item => item.label);
    expect(visibleLabels).toEqual([
      'Главная',
      'Лиды',
      'Заказы',
      'Календарь',
      'Клиенты',
      'Кондиционеры',
      'Подборки',
      'Оборудование',
    ]);
  });

  it('lets a partner owner configure only their document contour', () => {
    const partnerOwnerAuth = {
      capabilities: [
        ...tenantManagerAuth.capabilities,
        MANAGER_CAPABILITY.staffManage,
        MANAGER_CAPABILITY.analyticsManage,
        MANAGER_CAPABILITY.documentsManage,
      ],
    };

    expect(isManagerPathAllowed(partnerOwnerAuth, '/manager/settings/documents')).toBe(true);
    expect(isManagerPathAllowed(partnerOwnerAuth, '/manager/settings')).toBe(false);
    expect(isManagerPathAllowed(partnerOwnerAuth, '/manager/settings/backup')).toBe(false);
    expect(
      navSections.flatMap(section => section.items)
        .filter(item => !item.requiredCapability || partnerOwnerAuth.capabilities.includes(item.requiredCapability))
        .map(item => item.label),
    ).toContain('Документы CRM');
  });

  it('renders the safe projection without edit, supplier or price controls', async () => {
    const wrapper = mount(TenantCatalogView);
    await flushPromises();

    expect(mocks.listTenantCatalog).toHaveBeenCalledWith(1, 100, undefined, undefined);
    expect(wrapper.text()).toContain('Allowed Model');
    expect(wrapper.text()).toContain('1 750 BYN');
    expect(wrapper.text()).toContain('Разрешён');
    expect(wrapper.text()).toContain('Не разрешён');
    expect(wrapper.text()).not.toContain('Себестоимость');
    expect(wrapper.text()).not.toContain('Поставщик');
    expect(wrapper.findAll('button').map(button => button.text())).toEqual(['Найти', 'Назад', 'Далее']);
    expect(wrapper.findAll('a')).toHaveLength(0);
  });

  it('paginates the full catalog and resets page for search and availability filters', async () => {
    mocks.listTenantCatalog
      .mockResolvedValueOnce({ items: [], meta: { page: 1, limit: 100, total: 1235, pages: 13 } })
      .mockResolvedValueOnce({ items: [], meta: { page: 2, limit: 100, total: 1235, pages: 13 } })
      .mockResolvedValueOnce({ items: [], meta: { page: 1, limit: 100, total: 14, pages: 1 } })
      .mockResolvedValueOnce({ items: [], meta: { page: 1, limit: 100, total: 7, pages: 1 } });
    const wrapper = mount(TenantCatalogView);
    await flushPromises();

    expect(wrapper.text()).toContain('Страница 1 из 13');
    const nextButton = wrapper.findAll('button').find(button => button.text() === 'Далее');
    expect(nextButton).toBeDefined();
    await nextButton!.trigger('click');
    await flushPromises();
    expect(mocks.listTenantCatalog).toHaveBeenLastCalledWith(2, 100, undefined, undefined);
    expect(wrapper.text()).toContain('Страница 2 из 13');

    await wrapper.get('input[aria-label="Поиск по каталогу"]').setValue('Daikin');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(mocks.listTenantCatalog).toHaveBeenLastCalledWith(1, 100, 'Daikin', undefined);
    expect(wrapper.text()).toContain('Страница 1 из 1');

    await wrapper.get('select[aria-label="Фильтр доступности"]').setValue('allowed');
    await flushPromises();
    expect(mocks.listTenantCatalog).toHaveBeenLastCalledWith(1, 100, 'Daikin', true);
  });

  it('removes supplier fields from tenant equipment component commands', () => {
    const payload = {
      title: 'Indoor unit',
      supplier_id: null,
      supplier_invoice_number: 'INV-1',
      supplier_invoice_date: '2026-08-19T00:00:00',
    };
    expect(sanitizeEquipmentComponentPayload(payload, false)).toEqual({
      title: 'Indoor unit',
    });
    expect(sanitizeEquipmentComponentPayload(payload, true)).toEqual(payload);
  });

  it('uses only allowed tenant catalog products in the CRM product picker', async () => {
    mocks.listTenantCatalog.mockResolvedValueOnce({
      items: [allowedCatalogProduct],
      meta: { page: 1, limit: 20, total: 1, pages: 1 },
    });
    const products = await api.smartSearchProducts('Allowed', 20);

    expect(mocks.listTenantCatalog).toHaveBeenLastCalledWith(1, 20, 'Allowed', true);
    expect(products).toEqual([
      expect.objectContaining({
        id: 1,
        title: 'Allowed Model',
        price: 1750,
      }),
    ]);
    expect(products[0]).not.toHaveProperty('cost');
    expect(products[0]).not.toHaveProperty('supplier_id');
    expect(products[0]).not.toHaveProperty('source_url');
  });
});
