import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerContractsService, ManagerEquipmentService, ManagerService } from '../src/client';
import { api } from '../src/api';
import * as uiFeedback from '../src/services/ui-feedback';
import CustomerProfileView from '../src/views/CustomerProfileView.vue';
import App from '../src/App.vue';
import CustomerDetailsPanel from '../src/components/customers/CustomerDetailsPanel.vue';
import CustomerContactsPanel from '../src/components/customers/CustomerContactsPanel.vue';
import CustomerIntakeDialog from '../src/components/customers/CustomerIntakeDialog.vue';
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

describe('saved customer completeness', () => {
  it('keeps unsaved requisites out and permits partial dossier saving', async () => {
    const value = { ...customer, inn: null, phone: null, email: null };
    vi.mocked(api.getManagerCustomerDetail).mockResolvedValue(value as never);
    vi.spyOn(api, 'patchManagerCustomer').mockResolvedValue({ ...value, full_legal_name: 'Полное имя' } as never);
    const wrapper = mountProfile(); await flushPromises();
    const summary = () => wrapper.get('[aria-label="Заполненность досье"]');
    expect(summary().get('[data-completeness="contacts"]').text()).toContain('телефон, email');
    const details = wrapper.getComponent(CustomerDetailsPanel);
    await details.findAll('button').find(b => b.text() === 'Изменить')!.trigger('click');
    await details.get('input[placeholder="Полное наименование"]').setValue('Полное имя');
    expect(summary().get('[data-completeness="identity"]').text()).toContain('полное наименование, УНП');
    expect(details.get('button[type="submit"]').attributes('disabled')).toBeUndefined();
    await details.get('form').trigger('submit'); await flushPromises();
    expect(api.patchManagerCustomer).toHaveBeenCalledWith(7, { full_legal_name: 'Полное имя' });
    expect(summary().get('[data-completeness="identity"]').text()).not.toContain('полное наименование');
    expect(summary().get('[data-completeness="identity"]').text()).toContain('УНП');
  });
  it('updates saved additional contacts and recognition without reflecting typed values', async () => {
    const value = { ...customer, phone: null, email: null, contact_count: 0 };
    vi.mocked(api.getManagerCustomerDetail).mockResolvedValue(value as never);
    vi.spyOn(ManagerService, 'createManagerCustomerContact').mockResolvedValue({} as never);
    const wrapper = mountProfile(); await flushPromises();
    const contacts = wrapper.getComponent(CustomerContactsPanel);
    await contacts.findAll('button').find(b => b.text() === 'Добавить')!.trigger('click');
    await contacts.get('input[name="contact_name"]').setValue('Бухгалтер');
    await contacts.get('input[name="contact_email"]').setValue('new@example.test');
    const summary = () => wrapper.get('[aria-label="Заполненность досье"]');
    expect(summary().get('[data-completeness="contacts"]').text()).toContain('телефон, email');
    vi.mocked(ManagerService.getManagerCustomerContacts).mockResolvedValue({ items: [{ customer_id: 7, name: 'Бухгалтер', email: 'new@example.test', is_active: true, is_primary: false }] } as never);
    await contacts.get('form').trigger('submit'); await flushPromises();
    expect(summary().get('[data-completeness="contacts"]').text()).toContain('Не указаны: телефон');
    expect(summary().get('[data-completeness="contacts"]').text()).not.toContain('email');
    await wrapper.findAll('button').find(b => b.text() === 'Из реквизитов')!.trigger('click');
    wrapper.getComponent(CustomerIntakeDialog).vm.$emit('created', { ...value, inn: '987654321', full_legal_name: 'Распознанное имя', phone: '123' });
    await flushPromises();
    expect(summary().get('[data-completeness="identity"]').text()).toContain('Поля заполнены');
    expect(summary().get('[data-completeness="contacts"]').text()).toContain('Поля заполнены');
  });
  it('discards the old contact snapshot when recognition remounts the contacts panel', async () => {
    let resolveOld!: (value: never) => void;
    vi.mocked(api.getManagerCustomerDetail).mockResolvedValue({ ...customer, phone: null, email: null, contact_count: 2 } as never);
    vi.mocked(ManagerService.getManagerCustomerContacts).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    const wrapper = mountProfile(); await flushPromises();
    await wrapper.findAll('button').find(b => b.text() === 'Из реквизитов')!.trigger('click');
    vi.mocked(ManagerService.getManagerCustomerContacts).mockResolvedValue({ items: [] } as never);
    wrapper.getComponent(CustomerIntakeDialog).vm.$emit('created', { ...customer, phone: null, email: null, contact_count: 0 });
    await flushPromises();
    resolveOld({ items: [{ customer_id: 7, phone: 'old', email: 'old@example.test', is_active: true }] } as never);
    await flushPromises();
    expect(wrapper.get('[data-completeness="contacts"]').text()).toContain('телефон, email');
  });

  it('keeps hidden contacts lazy and unloaded secondary contacts unknown', async () => {
    vi.mocked(api.getManagerCustomerDetail).mockResolvedValue({ ...customer, phone: null, email: null, primary_contact: null, contact_count: 2 } as never);
    vi.spyOn(ManagerService, 'getManagerCustomerDocs').mockResolvedValue({ items: [] } as never);
    const wrapper = mountProfile('?customerId=7&openContract=1'); await flushPromises();
    expect(ManagerService.getManagerCustomerContacts).not.toHaveBeenCalled();
    expect(wrapper.get('[data-completeness="contacts"]').text()).toContain('ещё не загружены');
    expect(wrapper.get('[data-completeness="contacts"]').text()).not.toContain('Не указаны');
  });
  it('shows only the current client after navigation, even if an old request finishes later', async () => {
    const wrapper = await mountWorkspace();
    let resolveOld!: (value: never) => void;
    vi.mocked(api.getManagerCustomerDetail).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    wrapper.getComponent(CustomerContactsPanel).vm.$emit('updated'); await flushPromises();
    vi.mocked(api.getManagerCustomerDetail).mockResolvedValue({ ...customer, id: 8, name: 'Другой клиент', type: 'individual', phone: null, email: null, inn: null, signing_mode: 'self' } as never);
    window.history.pushState({}, '', '/manager/customers/profile?customerId=8'); window.dispatchEvent(new PopStateEvent('popstate'));
    await vi.waitFor(() => expect(wrapper.text()).toContain('Другой клиент'));
    resolveOld(customer as never); await flushPromises();
    expect(wrapper.get('[data-completeness="identity"]').text()).toContain('Не требуется для физлица');
    expect(wrapper.get('[data-completeness="contacts"]').text()).toContain('телефон, email');
    expect(wrapper.text()).not.toContain('ООО Клиент');
  });
});
