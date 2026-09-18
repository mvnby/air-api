import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import ProductImageCropDialog from '../src/components/ProductImageCropDialog.vue';
import {
  LOCAL_CROP_MAX_PIXELS,
  assessLocalCropSize,
  clampLocalCropRect,
  getLocalCropCapabilityError,
  localCropRotatedSize,
} from '../src/utils/product-image-local-crop';

const mounted: VueWrapper[] = [];
afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  document.body.innerHTML = '';
});

describe('local product image crop limits', () => {
  it('keeps crop coordinates inside the actual image', () => {
    expect(clampLocalCropRect({ x: -10, y: 85, width: 900, height: -1 }, { width: 120, height: 90 })).toEqual({
      x: 0,
      y: 85,
      width: 120,
      height: 1,
    });
  });

  it('reports oversized source images before allocating a canvas', () => {
    const width = 8_000;
    const height = Math.ceil((LOCAL_CROP_MAX_PIXELS + 1) / width);
    expect(assessLocalCropSize({ width, height }).error).toContain('слишком большое');
  });

  it('changes crop bounds after a quarter turn', () => {
    expect(localCropRotatedSize({ width: 120, height: 90 }, 1)).toEqual({ width: 90, height: 120 });
    expect(localCropRotatedSize({ width: 120, height: 90 }, 2)).toEqual({ width: 120, height: 90 });
  });

  it('tells the user when browser canvas support is unavailable', () => {
    const originalCreateImageBitmap = globalThis.createImageBitmap;
    vi.stubGlobal('createImageBitmap', undefined);
    expect(getLocalCropCapabilityError()).toContain('браузер');
    vi.stubGlobal('createImageBitmap', originalCreateImageBitmap);
  });

  it('keeps saving unavailable and explains a missing browser capability', async () => {
    vi.stubGlobal('createImageBitmap', undefined);
    const wrapper = mount(ProductImageCropDialog, {
      props: {
        open: true,
        productId: 7,
        image: { id: 9, url: 'https://images.example/crop.webp' },
      },
      attachTo: document.body,
    });
    mounted.push(wrapper);
    await flushPromises();

    expect(wrapper.text()).toContain('Этот браузер не умеет безопасно подготовить изображение локально');
    const saveButton = wrapper.findAll('button').find((button) => button.text() === 'Сохранить');
    expect(saveButton?.attributes('disabled')).toBeDefined();
  });
});
