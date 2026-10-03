import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerContractsService, ManagerEquipmentService, ManagerService } from '../src/client';
import { api } from '../src/api';
import * as uiFeedback from '../src/services/ui-feedback';
import CustomerProfileView from '../src/views/CustomerProfileView.vue';

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

beforeEach(() => {
  window.history.pushState({}, '', '/manager/customers');
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

  it('keeps the profile open when a contact has unsaved changes and leaving is declined', async () => {
    const wrapper = mountProfile();
    await flushPromises();
    // Edit the virtual legacy contact and change a field without saving.
    const contactEdit = wrapper.findAll('button').find((button) => button.text() === 'Изменить' && button.element.closest('.contact-row'));
    expect(contactEdit).toBeTruthy();
    await contactEdit!.trigger('click');
    await wrapper.get('input[name="contact_name"]').setValue('Анна');
    await wrapper.get('.back-link').trigger('click');
    await flushPromises();

    expect(uiFeedback.confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ title: 'Покинуть карточку?' }));
    expect(window.location.pathname).toBe('/manager/customers/profile');
    expect((wrapper.get('input[name="contact_name"]').element as HTMLInputElement).value).toBe('Анна');
  });
});
