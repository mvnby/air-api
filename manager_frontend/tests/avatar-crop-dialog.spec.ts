import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AvatarCropDialog from '../src/components/profile/AvatarCropDialog.vue';
import ImageCropSelector from '../src/components/ImageCropSelector.vue';

describe('personal avatar crop dialog', () => {
  afterEach(() => vi.restoreAllMocks());
  it('keeps server errors visible, blocks duplicate saves and releases its private preview', () => {
    const create = vi.fn().mockReturnValue('blob:avatar-preview');
    const revoke = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
    const file = new File(['photo'], 'face.png', { type: 'image/png' });
    const wrapper = mount(AvatarCropDialog, { props: { file, busy: true, errorMessage: 'Профиль изменился' }, global: { stubs: { teleport: true } } });
    expect(create).toHaveBeenCalledWith(file);
    expect(wrapper.get('[role="alert"]').text()).toContain('Профиль изменился');
    expect(wrapper.get('footer button:last-child').attributes('disabled')).toBeDefined();
    expect(wrapper.getComponent(ImageCropSelector).props('disabled')).toBe(true);
    wrapper.unmount(); expect(revoke).toHaveBeenCalledWith('blob:avatar-preview');
  });
});
