import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  logout: vi.fn(),
  listStorefronts: vi.fn(),
}));

vi.mock('../src/client', () => ({
  OpenAPI: {},
  LoginService: { logoutAccessToken: mocks.logout },
  ManagerService: { listManagerStorefronts: mocks.listStorefronts },
}));

import ManagerAccountMenu from '../src/components/manager/ManagerAccountMenu.vue';
import { MANAGER_CAPABILITY } from '../src/manager-capabilities';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

describe('manager account menu', () => {
  beforeEach(() => {
    managerStorefrontSelection.storefronts.value = [{
      id: 71,
      tenant_id: 21,
      slug: 'vitebsk',
      display_name: 'Витебск',
      status: 'active',
      city: null,
      default_locale: 'ru-BY',
      currency: 'BYN',
      is_default: true,
      is_current: true,
    }];
    managerStorefrontSelection.selectedSlug.value = 'vitebsk';
  });

  it('shows account identity and routes owner actions from one menu', async () => {
    const wrapper = mount(ManagerAccountMenu, {
      props: {
        auth: {
          username: 'owner-vitebsk',
          display_name: 'Максим Коротов',
          status: 'active',
          tenant_id: 21,
          storefront_id: 71,
          capabilities: [
            MANAGER_CAPABILITY.analyticsManage,
            MANAGER_CAPABILITY.infrastructureManage,
          ],
        },
      },
    });

    expect(wrapper.text()).toContain('Максим Коротов');
    expect(wrapper.text()).toContain('Витебск');
    await wrapper.get('[aria-haspopup="menu"]').trigger('click');
    expect(wrapper.text()).toContain('Профиль и пароль');
    expect(wrapper.text()).toContain('Интеграции');
    expect(wrapper.text()).toContain('Настройки сайта');

    const integrations = wrapper.findAll('[role="menuitem"]')
      .find(button => button.text().includes('Интеграции'));
    await integrations!.trigger('click');
    expect(wrapper.emitted('navigate')).toEqual([['/manager/integrations']]);
  });

  it('does not expose integration settings to a manager', async () => {
    const wrapper = mount(ManagerAccountMenu, {
      props: {
        auth: {
          username: 'manager-vitebsk',
          display_name: 'Менеджер',
          status: 'active',
          tenant_id: 21,
          storefront_id: 71,
          capabilities: [MANAGER_CAPABILITY.crmManage],
        },
      },
    });

    await wrapper.get('[aria-haspopup="menu"]').trigger('click');
    expect(wrapper.text()).not.toContain('Интеграции');
    expect(wrapper.text()).not.toContain('Документы CRM');
    expect(wrapper.text()).not.toContain('Настройки сайта');
  });

  it('routes a document owner to CRM document settings without infrastructure access', async () => {
    const wrapper = mount(ManagerAccountMenu, {
      props: {
        auth: {
          username: 'documents-owner-vitebsk',
          display_name: 'Владелец документов',
          status: 'active',
          tenant_id: 21,
          storefront_id: 71,
          capabilities: [MANAGER_CAPABILITY.documentsManage],
        },
      },
    });

    await wrapper.get('[aria-haspopup="menu"]').trigger('click');

    expect(wrapper.text()).toContain('Документы CRM');
    expect(wrapper.text()).not.toContain('Настройки сайта');
    await wrapper.get('[data-testid="manager-document-settings"]').trigger('click');
    expect(wrapper.emitted('navigate')).toEqual([['/manager/settings/documents']]);
  });
});
