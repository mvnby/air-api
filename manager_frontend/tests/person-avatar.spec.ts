import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import PersonAvatar from '../src/components/common/PersonAvatar.vue';
describe('private person avatar', () => {
  it('uses initials and never loads an arbitrary external or unrelated URL', async () => {
    const wrapper = mount(PersonAvatar, { props: { name: 'Мария Иванова', src: 'https://tracking.example/face.png' } });
    expect(wrapper.text()).toBe('МИ'); expect(wrapper.find('img').exists()).toBe(false);
    await wrapper.setProps({ src: '/media/shared-face.png' }); expect(wrapper.find('img').exists()).toBe(false);
    await wrapper.setProps({ src: '/api/manager/staff/7/avatar?v=missing-company' }); expect(wrapper.find('img').exists()).toBe(false);
    wrapper.unmount();
  });
  it('loads the authenticated versioned endpoint and recovers from a failed image', async () => {
    const wrapper = mount(PersonAvatar, { props: { name: 'Мария Иванова', src: '/api/manager/staff/7/avatar?tenant_id=2&v=first' } });
    expect(wrapper.get('img').attributes('src')).toBe('/api/manager/staff/7/avatar?tenant_id=2&v=first');
    await wrapper.get('img').trigger('error'); expect(wrapper.text()).toBe('МИ');
    await wrapper.setProps({ src: '/api/manager/staff/7/avatar?tenant_id=2&v=second' }); expect(wrapper.find('img').exists()).toBe(true);
    wrapper.unmount();
  });
});
