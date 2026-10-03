import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerContractsService, ManagerEquipmentService, ManagerService } from '../src/client';
import { api } from '../src/api';
import * as uiFeedback from '../src/services/ui-feedback';
import CustomerProfileView from '../src/views/CustomerProfileView.vue';
import App from '../src/App.vue';
import { clearManagerSession } from '../src/services/manager-session';
import { storefrontSettingsApi } from '../src/features/settings/storefront-settings-api';

const customer = {
  id: 7, name: 'ООО Клиент', type: 'company', phone: '+375291110000',
  email: 'team@example.test', inn: '123456789', signing_mode: 'statutory_body',
  order_count: 2, branches: [], is_archived: false,
};
const wrappers: VueWrapper[] = [];
function mountProfile(search = '?customerId=7') {
  window.history.pushState({}, '', `/manager/customers/profile${search}`);
  const wrapper = mount(CustomerProfileView, {
    global: { stubs: { teleport: true, transition: false, CreateOrderModal: true, CustomerIntakeDialog: true } },
  });
  wrappers.push(wrapper);
  return wrapper;
}
async function mountWorkspace(search = '?customerId=7') {
  window.history.replaceState({}, '', `/manager/customers/profile${search}`);
  const wrapper = mount(App, {
    global: { stubs: { UiFeedbackHost: true, CreateOrderModal: true, CustomerIntakeDialog: true } },
  });
  wrappers.push(wrapper);
  await vi.waitFor(() => expect(wrapper.find('.back-link').exists()).toBe(true));
  await flushPromises();
  return wrapper;
}

async function editContact(wrapper: VueWrapper) {
  const contactEdit = wrapper.findAll('button').find((button) => button.element.closest('.contact-row') && button.text() === 'Изменить');
  expect(contactEdit).toBeTruthy();
  await contactEdit!.trigger('click');
  await wrapper.get('input[name="contact_name"]').setValue('Анна');
}

beforeEach(() => {
  clearManagerSession();
  window.localStorage.clear();
  window.history.pushState({}, '', '/manager/customers');
  vi.spyOn(ManagerService, 'readUserMe').mockResolvedValue({ username: 'manager', role: 'manager', tenant_id: 1, storefront_id: 1, capabilities: ['crm.manage'] } as never);
  vi.spyOn(ManagerService, 'listManagerStorefronts').mockResolvedValue({ items: [{ slug: 'mvn', display_name: 'MVN', is_current: true, is_default: true }] } as never);
  vi.spyOn(storefrontSettingsApi, 'brand').mockResolvedValue({ display_name: 'MVN', logo_url: null, compact_logo_url: null } as never);
  vi.spyOn(api, 'getLeadsCounter').mockResolvedValue({ count: 0 } as never);
  vi.spyOn(api, 'getManagerCustomers').mockResolvedValue({ items: [customer], meta: { page: 1, limit: 20, total: 1, pages: 1 } } as never);
  vi.spyOn(api, 'getManagerCustomerDetail').mockResolvedValue(customer as never);
  vi.spyOn(ManagerService, 'getManagerCustomerContacts').mockResolvedValue({ items: [] } as never);
  vi.spyOn(ManagerEquipmentService, 'listManagerEquipment').mockResolvedValue({ items: [], meta: { pages: 1 } } as never);
  vi.spyOn(ManagerService, 'getManagerCustomerReconciliation').mockResolvedValue({
    opening_balance: 0, closing_balance: 0, documents: [], payments: [], warnings: [], ready_for_generation: false,
  } as never);
  vi.spyOn(ManagerContractsService, 'getManagerCustomerContracts').mockResolvedValue({ items: [] } as never);
  vi.spyOn(uiFeedback, 'confirmDialog').mockResolvedValue(false);
});
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  clearManagerSession();
  vi.restoreAllMocks();
  window.history.pushState({}, '', '/manager/customers');
});

describe('CustomerProfileView workspace', () => {
  it('opens on contacts and loads heavy sections only after their tabs are selected', async () => {
    const wrapper = mountProfile();
    await flushPromises();
    expect(wrapper.text()).toContain('ООО Клиент');
    expect(ManagerService.getManagerCustomerContacts).toHaveBeenCalledWith(7);
    expect(ManagerEquipmentService.listManagerEquipment).not.toHaveBeenCalled();
    expect(ManagerService.getManagerCustomerReconciliation).not.toHaveBeenCalled();

    const tabs = wrapper.findAll('nav.customer-tabs button');
    await tabs.find((tab) => tab.text() === 'Оборудование')!.trigger('click');
    await flushPromises();
    await vi.waitFor(() => expect(ManagerEquipmentService.listManagerEquipment).toHaveBeenCalled());
    expect(ManagerService.getManagerCustomerReconciliation).not.toHaveBeenCalled();

    await tabs.find((tab) => tab.text() === 'Взаиморасчёты')!.trigger('click');
    await flushPromises();
    await vi.waitFor(() => expect(ManagerService.getManagerCustomerReconciliation).toHaveBeenCalledWith(7, expect.any(String), expect.any(String), null));
  });

  it('returns from the profile to the customer list through the App router', async () => {
    const wrapper = await mountWorkspace();
    await wrapper.get('.back-link').trigger('click');
    await vi.waitFor(() => expect(wrapper.find('.customer-name-link').exists()).toBe(true));
    expect(window.location.pathname).toBe('/manager/customers');
    expect(wrapper.find('.back-link').exists()).toBe(false);
    expect(uiFeedback.confirmDialog).not.toHaveBeenCalled();
  });

  it('keeps the profile open when a contact has unsaved changes and leaving is declined', async () => {
    const wrapper = await mountWorkspace();
    await editContact(wrapper);
    await wrapper.get('.back-link').trigger('click');
    await flushPromises();

    expect(uiFeedback.confirmDialog).toHaveBeenCalledTimes(1);
    expect(uiFeedback.confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ title: 'Покинуть карточку?' }));
    expect(window.location.pathname).toBe('/manager/customers/profile');
    expect((wrapper.get('input[name="contact_name"]').element as HTMLInputElement).value).toBe('Анна');
  });

  it('checks unsaved changes once and returns to the list when leaving is confirmed', async () => {
    vi.mocked(uiFeedback.confirmDialog).mockResolvedValue(true);
    const wrapper = await mountWorkspace();
    await editContact(wrapper);
    await wrapper.get('.back-link').trigger('click');
    await vi.waitFor(() => expect(wrapper.find('.customer-name-link').exists()).toBe(true));
    expect(window.location.pathname).toBe('/manager/customers');
    expect(uiFeedback.confirmDialog).toHaveBeenCalledTimes(1);
  });

  it('preserves the return destination including list filters', async () => {
    const wrapper = await mountWorkspace(`?customerId=7&returnTo=${encodeURIComponent('/manager/customers?type=company')}`);
    await wrapper.get('.back-link').trigger('click');
    await vi.waitFor(() => expect(wrapper.find('.customer-name-link').exists()).toBe(true));
    expect(`${window.location.pathname}${window.location.search}`).toBe('/manager/customers?type=company');
  });
});
