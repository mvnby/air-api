<script lang="ts">
export type ImageCropValue = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ImageCropSourceSize = {
  width: number;
  height: number;
};
</script>

<script setup lang="ts">
import { computed, ref } from 'vue';

type CropHandle = 'nw' | 'ne' | 'sw' | 'se';
type DragMode = 'draw' | 'move' | CropHandle;
type CropPoint = { x: number; y: number };
type DragState = {
  mode: DragMode;
  startPoint: CropPoint;
  startRect: ImageCropValue;
  anchor?: CropPoint;
};

const props = withDefaults(defineProps<{
  src: string;
  modelValue: ImageCropValue;
  sourceWidth: number;
  sourceHeight: number;
  minSize?: number;
  imageAlt?: string;
  disabled?: boolean;
}>(), {
  minSize: 1,
  imageAlt: '',
  disabled: false,
});

const emit = defineEmits<{
  'update:modelValue': [value: ImageCropValue];
  'source-load': [size: ImageCropSourceSize];
}>();

const imageEl = ref<HTMLImageElement | null>(null);
const dragState = ref<DragState | null>(null);

const normalizedMinSize = computed(() => Math.max(1, Math.trunc(props.minSize)));

const hasSourceSize = computed(() => props.sourceWidth > 0 && props.sourceHeight > 0);

const selectionStyle = computed(() => {
  if (!hasSourceSize.value || !props.modelValue.width || !props.modelValue.height) {
    return { display: 'none' };
  }

  return {
    left: `${Math.max(0, Math.min(100, (props.modelValue.x / props.sourceWidth) * 100))}%`,
    top: `${Math.max(0, Math.min(100, (props.modelValue.y / props.sourceHeight) * 100))}%`,
    width: `${Math.max(0, Math.min(100, (props.modelValue.width / props.sourceWidth) * 100))}%`,
    height: `${Math.max(0, Math.min(100, (props.modelValue.height / props.sourceHeight) * 100))}%`,
  };
});

const handleControls: Array<{
  key: CropHandle;
  label: string;
  className: string;
}> = [
  {
    key: 'nw',
    label: 'Левый верхний угол',
    className: 'left-0 top-0 -translate-x-1/2 -translate-y-1/2 cursor-nwse-resize',
  },
  {
    key: 'ne',
    label: 'Правый верхний угол',
    className: 'right-0 top-0 translate-x-1/2 -translate-y-1/2 cursor-nesw-resize',
  },
  {
    key: 'sw',
    label: 'Левый нижний угол',
    className: 'bottom-0 left-0 -translate-x-1/2 translate-y-1/2 cursor-nesw-resize',
  },
  {
    key: 'se',
    label: 'Правый нижний угол',
    className: 'bottom-0 right-0 translate-x-1/2 translate-y-1/2 cursor-nwse-resize',
  },
];

const clampRect = (rect: ImageCropValue): ImageCropValue => {
  if (!hasSourceSize.value) return { x: 0, y: 0, width: 0, height: 0 };

  const sourceWidth = props.sourceWidth;
  const sourceHeight = props.sourceHeight;
  const minSize = Math.min(normalizedMinSize.value, sourceWidth, sourceHeight);
  const maxX = Math.max(0, sourceWidth - minSize);
  const maxY = Math.max(0, sourceHeight - minSize);
  const x = Math.max(0, Math.min(Math.trunc(rect.x), maxX));
  const y = Math.max(0, Math.min(Math.trunc(rect.y), maxY));
  const width = Math.max(minSize, Math.min(Math.trunc(rect.width), sourceWidth - x));
  const height = Math.max(minSize, Math.min(Math.trunc(rect.height), sourceHeight - y));

  return { x, y, width, height };
};

const getPointFromEvent = (event: PointerEvent): CropPoint | null => {
  const image = imageEl.value;
  if (!image || !hasSourceSize.value) return null;

  const rect = image.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;

  const relativeX = Math.max(0, Math.min(event.clientX - rect.left, rect.width));
  const relativeY = Math.max(0, Math.min(event.clientY - rect.top, rect.height));

  return {
    x: Math.round((relativeX / rect.width) * props.sourceWidth),
    y: Math.round((relativeY / rect.height) * props.sourceHeight),
  };
};

const getAnchorForHandle = (handle: CropHandle, rect: ImageCropValue): CropPoint => {
  const right = rect.x + rect.width;
  const bottom = rect.y + rect.height;

  if (handle === 'nw') return { x: right, y: bottom };
  if (handle === 'ne') return { x: rect.x, y: bottom };
  if (handle === 'sw') return { x: right, y: rect.y };
  return { x: rect.x, y: rect.y };
};

const rectFromCorners = (anchor: CropPoint, point: CropPoint): ImageCropValue => {
  const minSize = normalizedMinSize.value;
  let x = Math.min(anchor.x, point.x);
  let y = Math.min(anchor.y, point.y);
  let width = Math.abs(point.x - anchor.x);
  let height = Math.abs(point.y - anchor.y);

  if (width < minSize) {
    if (point.x < anchor.x) x = anchor.x - minSize;
    width = minSize;
  }
  if (height < minSize) {
    if (point.y < anchor.y) y = anchor.y - minSize;
    height = minSize;
  }

  return clampRect({ x, y, width, height });
};

const updateCrop = (value: ImageCropValue) => {
  emit('update:modelValue', clampRect(value));
};

const getPointerMode = (target: EventTarget | null): DragMode => {
  if (!(target instanceof HTMLElement)) return 'draw';

  const handle = target.closest<HTMLElement>('[data-crop-handle]');
  if (handle?.dataset.cropHandle) return handle.dataset.cropHandle as CropHandle;

  const selection = target.closest<HTMLElement>('[data-crop-selection]');
  return selection ? 'move' : 'draw';
};

const onPointerDown = (event: PointerEvent) => {
  if (props.disabled) return;
  event.preventDefault();

  const point = getPointFromEvent(event);
  if (!point) return;

  const mode = getPointerMode(event.target);
  const startRect = clampRect(props.modelValue);
  const anchor = mode === 'draw'
    ? point
    : mode === 'move'
      ? undefined
      : getAnchorForHandle(mode, startRect);

  dragState.value = { mode, startPoint: point, startRect, anchor };

  if (mode === 'draw') {
    updateCrop({ x: point.x, y: point.y, width: normalizedMinSize.value, height: normalizedMinSize.value });
  }

  try {
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  } catch {
    // Pointer capture can fail for synthetic or already-ended events.
  }
};

const onPointerMove = (event: PointerEvent) => {
  if (!dragState.value || props.disabled) return;
  event.preventDefault();

  const point = getPointFromEvent(event);
  if (!point) return;

  const state = dragState.value;
  if (state.mode === 'move') {
    const deltaX = point.x - state.startPoint.x;
    const deltaY = point.y - state.startPoint.y;
    updateCrop({
      ...state.startRect,
      x: state.startRect.x + deltaX,
      y: state.startRect.y + deltaY,
    });
    return;
  }

  const anchor = state.anchor || state.startPoint;
  updateCrop(rectFromCorners(anchor, point));
};

const onPointerUp = (event: PointerEvent) => {
  if (!dragState.value) return;
  event.preventDefault();
  dragState.value = null;

  try {
    (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
  } catch {
    // Pointer capture may already be released by the browser.
  }
};

const onImageLoad = (event: Event) => {
  const image = event.target as HTMLImageElement;
  emit('source-load', {
    width: image.naturalWidth,
    height: image.naturalHeight,
  });
};
</script>

<template>
  <div
    class="flex w-full justify-center"
    :class="{ 'opacity-60': disabled }"
  >
    <div
      class="relative inline-block max-h-[56vh] max-w-full cursor-crosshair touch-none select-none overflow-hidden rounded-md bg-white"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dragstart.prevent
    >
      <img
        ref="imageEl"
        :src="src"
        :alt="imageAlt"
        draggable="false"
        class="block max-h-[56vh] max-w-full select-none object-contain"
        @load="onImageLoad"
      />
      <div class="pointer-events-none absolute inset-0">
        <div
          class="absolute pointer-events-auto cursor-move border-2 border-teal-500 bg-teal-500/10 shadow-[0_0_0_9999px_rgba(15,23,42,0.30)]"
          :style="selectionStyle"
          data-crop-selection="true"
        >
          <button
            v-for="handle in handleControls"
            :key="handle.key"
            type="button"
            class="absolute z-10 flex h-8 w-8 items-center justify-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2"
            :class="handle.className"
            :data-crop-handle="handle.key"
            :aria-label="handle.label"
            :title="handle.label"
          >
            <span class="block h-3.5 w-3.5 rounded-full border-2 border-white bg-teal-500 shadow-md"></span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
