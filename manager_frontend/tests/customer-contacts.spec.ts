import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerService } from '../src/client';
import CustomerContactsPanel from '../src/components/customers/CustomerContactsPanel.vue';

const customer = {
  id: 7, name: 'ООО Клиент', type: 'company', phone: '+375291110000',
  email: 'legacy@example.test', order_count: 0,
};
const primary = { id: 11, customer_id: 7, name: 'Анна', role: 'Закупки', phone: '+375291110000', email: 'anna@example.test', is_primary: true, is_active: true };
const secondary = { id: 12, customer_id: 7, name: 'Игорь', role: 'Бухгалтер', phone: '+375291112222', email: null, is_primary: false, is_active: true };
const wrappers: VueWrapper[] = [];
function mountPanel(editInitially = false) {
  const wrapper = mount(CustomerContactsPanel, { props: { customer: customer as never, editInitially } });
  wrappers.push(wrapper);
  return wrapper;
}

beforeEach(() => {
  vi.spyOn(ManagerService, 'getManagerCustomerContacts').mockResolvedValue({ items: [primary, secondary] } as never);
  vi.spyOn(ManagerService, 'getManagerCustomerContactHistory').mockResolvedValue({ items: [] } as never);
  vi.spyOn(ManagerService, 'patchManagerCustomerContact').mockResolvedValue(primary as never);
  vi.spyOn(ManagerService, 'createManagerCustomerContact').mockResolvedValue(primary as never);
});
afterEach(() => { wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); vi.restoreAllMocks(); });

describe('CustomerContactsPanel', () => {
  it('edits the designated primary and leaves the secondary out of that request', async () => {
    const wrapper = mountPanel(true);
    await flushPromises();
    expect((wrapper.get('input[name="contact_name"]').element as HTMLInputElement).value).toBe('Анна');
    await wrapper.get('input[name="contact_phone"]').setValue('+375291113333');
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true]);
    await wrapper.get('form.contact-form').trigger('submit');
    await flushPromises();

    expect(ManagerService.patchManagerCustomerContact).toHaveBeenCalledWith(7, 11, expect.objectContaining({
      name: 'Анна', phone: '+375291113333', is_primary: true,
    }));
    expect(wrapper.emitted('updated')).toHaveLength(1);
    expect(ManagerService.patchManagerCustomerContact).toHaveBeenCalledTimes(1);
  });

  it('preserves the edited secondary contact when saving fails', async () => {
    vi.mocked(ManagerService.patchManagerCustomerContact).mockRejectedValueOnce(new Error('offline'));
    const wrapper = mountPanel();
    await flushPromises();
    await wrapper.get('button[aria-label="Изменить контакт Игорь"]').trigger('click');
    await wrapper.get('input[name="contact_role"]').setValue('Главный бухгалтер');
    await wrapper.get('form.contact-form').trigger('submit');
    await flushPromises();

    expect(ManagerService.patchManagerCustomerContact).toHaveBeenCalledWith(7, 12, expect.objectContaining({
      role: 'Главный бухгалтер', is_primary: false,
    }));
    expect(wrapper.get('[role="alert"]').text()).toContain('offline');
    expect((wrapper.get('input[name="contact_role"]').element as HTMLInputElement).value).toBe('Главный бухгалтер');
    expect(wrapper.emitted('updated')).toBeUndefined();
  });

  it('offers legacy phone/email as a virtual contact and creates a real primary on edit', async () => {
    vi.mocked(ManagerService.getManagerCustomerContacts).mockResolvedValue({ items: [] } as never);
    const wrapper = mountPanel(true);
    await flushPromises();
    expect(wrapper.text()).toContain('Изменить контакт');
    expect((wrapper.get('input[name="contact_phone"]').element as HTMLInputElement).value).toBe('+375291110000');
    await wrapper.get('input[name="contact_name"]').setValue('Анна');
    await wrapper.get('form.contact-form').trigger('submit');
    await flushPromises();

    expect(ManagerService.createManagerCustomerContact).toHaveBeenCalledWith(7, expect.objectContaining({
      name: 'Анна', phone: '+375291110000', email: 'legacy@example.test', is_primary: true,
    }));
    expect(ManagerService.patchManagerCustomerContact).not.toHaveBeenCalled();
  });

  it('loads change history only when opened', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(ManagerService.getManagerCustomerContactHistory).not.toHaveBeenCalled();
    await wrapper.get('button[aria-expanded="false"]').trigger('click');
    await flushPromises();
    expect(ManagerService.getManagerCustomerContactHistory).toHaveBeenCalledWith(7);
  });
});
