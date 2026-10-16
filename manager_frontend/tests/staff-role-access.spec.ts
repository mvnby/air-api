import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import InstallerEditModal from '../src/components/InstallerEditModal.vue';
import { managerSession } from '../src/services/manager-session';
import { api } from '../src/api';

describe('employee role controls', () => {
  beforeEach(() => { managerSession.auth.value = { role: 'admin' } as any; });
  it('offers the five membership roles and prevents an admin assigning owner', async () => {
    const wrapper = mount(InstallerEditModal, { props: { modelValue: false }, global: { stubs: { teleport: true } } });
    await wrapper.setProps({ modelValue: true });
    const roles = wrapper.get('select');
    expect(roles.findAll('option').map(option => option.attributes('value'))).toEqual(['owner', 'admin', 'manager', 'catalog_editor', 'installer']);
    expect(roles.get('option[value="owner"]').attributes('disabled')).toBeDefined();
    await roles.setValue('catalog_editor');
    expect((roles.element as HTMLSelectElement).value).toBe('catalog_editor');
    wrapper.unmount();
  });
  it('prevents owner changes from an admin and explains the restriction', async () => {
    const update = vi.spyOn(api, 'patchManagerStaff').mockResolvedValue({} as any);
    const wrapper = mount(InstallerEditModal, { props: { modelValue: false, staffUser: { id: 4, display_name: 'Владелец', primary_role: 'owner', status: 'active' } as any }, global: { stubs: { teleport: true } } });
    await wrapper.setProps({ modelValue: true });
    expect(wrapper.get('select').attributes('disabled')).toBeDefined();
    expect(wrapper.text()).toContain('Профиль владельца может изменять только владелец компании');
    const save = wrapper.findAll('button').find(button => button.text().includes('Сохранить'))!;
    expect(save.attributes('disabled')).toBeDefined();
    await save.trigger('click');
    await flushPromises();
    expect(update).not.toHaveBeenCalled();
    wrapper.unmount();
    update.mockRestore();
  });
  it('allows a company owner to select an owner role', async () => {
    managerSession.auth.value = { role: 'owner' } as any;
    const wrapper = mount(InstallerEditModal, { props: { modelValue: false }, global: { stubs: { teleport: true } } });
    await wrapper.setProps({ modelValue: true });
    expect(wrapper.get('option[value="owner"]').attributes('disabled')).toBeUndefined();
    wrapper.unmount();
  });
});
