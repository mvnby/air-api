<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useFacsimileEditor } from '../composables/use-facsimile-editor';
import { pagePoint, stampRatio, type FacsimileKind, type StampPlacement } from '../model/facsimile-placement';

const props = defineProps<{ documentId: number; title: string }>();
const emit = defineEmits<{ close: []; saved: [] }>();
const editor = useFacsimileEditor();
const { preview, placement, page, selected, currentPage, pageUrl, assetUrls, loading, pageLoading, saving, error } = editor;
const dialog = ref<HTMLDialogElement | null>(null);
const pageElement = ref<HTMLElement | null>(null);
const zoom = ref(1);
const pageLoaded = ref(false);
const assetsLoaded = ref({ signature: false, seal: false });
const kinds: FacsimileKind[] = ['signature', 'seal'];
const labels = { signature: 'Подпись', seal: 'Печать' };
const pageIndex = computed(() => preview.value?.pages.findIndex((item) => item.page_number === currentPage.value) ?? 0);
const canSave = computed(() => preview.value?.can_save && pageLoaded.value && assetsLoaded.value.signature && assetsLoaded.value.seal && !loading.value && !pageLoading.value && !saving.value && !error.value);
let gesture: { pointerId: number; kind: FacsimileKind; mode: 'drag' | 'resize'; start: { x_mm: number; y_mm: number }; stamp: StampPlacement } | null = null;
const close = () => {
  if (saving.value) return;
  editor.close();
  emit('close');
};
watch(() => props.documentId, (id) => {
  gesture = null; zoom.value = 1; assetsLoaded.value = { signature: false, seal: false };
  void editor.open(id);
}, { immediate: true });
watch(pageUrl, () => { pageLoaded.value = false; gesture = null; });
onMounted(async () => { await nextTick(); dialog.value?.showModal(); });
const stampStyle = (kind: FacsimileKind) => {
  if (!placement.value || !page.value || !preview.value) return {};
  const stamp = placement.value[kind];
  return {
    left: `${stamp.x_mm / page.value.width_mm * 100}%`,
    top: `${stamp.y_mm / page.value.height_mm * 100}%`,
    width: `${stamp.width_mm / page.value.width_mm * 100}%`,
    aspectRatio: `${preview.value[kind].width_px} / ${preview.value[kind].height_px}`,
  };
};
const point = (event: { clientX: number; clientY: number }) => pagePoint(event.clientX, event.clientY, pageElement.value!.getBoundingClientRect(), page.value!);
const beginGesture = (event: PointerEvent, kind: FacsimileKind, mode: 'drag' | 'resize') => {
  if (!preview.value?.can_save || saving.value || !pageLoaded.value || !pageElement.value || !placement.value || event.button !== 0) return;
  event.preventDefault();
  selected.value = kind;
  gesture = { pointerId: event.pointerId, kind, mode, start: point(event), stamp: { ...placement.value[kind] } };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
};
const moveGesture = (event: PointerEvent) => {
  if (!gesture || event.pointerId !== gesture.pointerId || !pageElement.value || !page.value || !preview.value) return;
  const current = point(event);
  const dx = current.x_mm - gesture.start.x_mm;
  const dy = current.y_mm - gesture.start.y_mm;
  const next = { ...gesture.stamp };
  if (gesture.mode === 'drag') { next.x_mm += dx; next.y_mm += dy; }
  else {
    const ratio = stampRatio(preview.value[gesture.kind]);
    next.width_mm += (dx + ratio * dy) / (1 + ratio * ratio);
    // Resize stays anchored at the upper left edge of the stamp.
    next.width_mm = Math.min(next.width_mm, page.value.width_mm - next.x_mm, (page.value.height_mm - next.y_mm) / ratio);
  }
  editor.updateStamp(gesture.kind, next);
};
const endGesture = (event: PointerEvent) => { if (gesture?.pointerId === event.pointerId) gesture = null; };
const place = (event: MouseEvent) => {
  if (!pageLoaded.value || !placement.value || !preview.value || !pageElement.value || saving.value) return;
  const current = point(event);
  const stamp = placement.value[selected.value];
  editor.updateStamp(selected.value, { ...stamp, page_number: currentPage.value, x_mm: current.x_mm - stamp.width_mm / 2, y_mm: current.y_mm - stamp.width_mm * stampRatio(preview.value[selected.value]) / 2 });
};
const adjust = (event: KeyboardEvent, kind: FacsimileKind) => {
  if (!placement.value || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-'].includes(event.key)) return;
  event.preventDefault(); selected.value = kind;
  const stamp = { ...placement.value[kind] };
  const step = event.shiftKey ? 2 : 0.5;
  if (event.key === 'ArrowLeft') stamp.x_mm -= step;
  if (event.key === 'ArrowRight') stamp.x_mm += step;
  if (event.key === 'ArrowUp') stamp.y_mm -= step;
  if (event.key === 'ArrowDown') stamp.y_mm += step;
  if (['+', '='].includes(event.key)) stamp.width_mm += step;
  if (event.key === '-') stamp.width_mm -= step;
  editor.updateStamp(kind, stamp);
};
const resizeSelected = (amount: number) => {
  if (!placement.value || !page.value || placement.value[selected.value].page_number !== currentPage.value) return;
  const stamp = placement.value[selected.value];
  editor.updateStamp(selected.value, { ...stamp, width_mm: stamp.width_mm * amount });
};
const changePage = (offset: number) => {
  gesture = null;
  const target = preview.value?.pages[pageIndex.value + offset];
  if (target) void editor.setPage(target.page_number);
};
const save = async () => { if (canSave.value && await editor.save()) emit('saved'); };
const reload = () => {
  gesture = null; assetsLoaded.value = { signature: false, seal: false };
  void editor.open(props.documentId);
};
const assetLoaded = (event: Event, kind: FacsimileKind) => {
  if ((event.target as HTMLImageElement).src === assetUrls.value[kind]) assetsLoaded.value[kind] = true;
};
const pageImageLoaded = (event: Event) => {
  if ((event.target as HTMLImageElement).src === pageUrl.value) pageLoaded.value = true;
};
const imageError = () => { error.value = 'Не удалось показать изображение. Обновите предпросмотр.'; };
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="facsimile-dialog" aria-labelledby="facsimile-editor-title" aria-describedby="facsimile-editor-help" @cancel.prevent="close">
      <div class="flex h-full flex-col">
        <header class="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
          <div class="min-w-0">
            <h2 id="facsimile-editor-title" class="text-base font-bold">Подпись и печать на PDF</h2>
            <p class="truncate text-sm text-slate-500">{{ title }}</p>
          </div>
          <button class="editor-button" type="button" aria-label="Закрыть редактор" :disabled="saving" @click="close">Закрыть</button>
        </header>
        <div v-if="preview" class="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-2 dark:border-slate-700 dark:bg-slate-900">
          <div class="flex items-center gap-1" aria-label="Страницы PDF">
            <button class="editor-button" type="button" aria-label="Предыдущая страница" :disabled="pageIndex <= 0 || saving" @click="changePage(-1)">←</button>
            <span class="px-1 text-sm" aria-live="polite">{{ currentPage }} / {{ preview.pages.length }}</span>
            <button class="editor-button" type="button" aria-label="Следующая страница" :disabled="pageIndex >= preview.pages.length - 1 || saving" @click="changePage(1)">→</button>
          </div>
          <button v-for="kind in kinds" :key="kind" class="editor-button" :class="{ 'editor-selected': selected === kind }" type="button" :aria-pressed="selected === kind" :disabled="saving || !preview.can_save" @click="selected = kind">{{ labels[kind] }}<span v-if="placement && placement[kind].page_number !== currentPage"> · стр. {{ placement[kind].page_number }}</span></button>
          <div v-if="preview.can_save" class="flex items-center gap-1">
            <button class="editor-button" type="button" :aria-label="`Уменьшить: ${labels[selected]}`" :disabled="saving || !placement || placement[selected].page_number !== currentPage" @click="resizeSelected(0.9)">−</button>
            <span class="text-xs text-slate-500">Размер</span>
            <button class="editor-button" type="button" :aria-label="`Увеличить: ${labels[selected]}`" :disabled="saving || !placement || placement[selected].page_number !== currentPage" @click="resizeSelected(1.1)">+</button>
          </div>
          <button class="editor-button" type="button" :aria-pressed="zoom === 2" @click="zoom = zoom === 1 ? 2 : 1">{{ zoom === 1 ? 'Приблизить' : 'Вся страница' }}</button>
        </div>
        <p id="facsimile-editor-help" class="shrink-0 px-4 py-2 text-xs text-slate-600 dark:text-slate-300">Выберите подпись или печать и нажмите на нужное место страницы. Перетаскивайте изображение, меняйте размер за угол. Стрелки клавиатуры — точное перемещение, +/− — размер.</p>
        <div v-if="error" role="alert" class="flex shrink-0 flex-wrap items-center gap-2 bg-rose-50 px-4 py-2 text-sm text-rose-700"><span>{{ error }}</span><button class="editor-button" type="button" :disabled="saving || loading" @click="reload">Обновить предпросмотр</button></div>
        <p v-if="preview && !preview.can_save" class="shrink-0 bg-amber-50 px-4 py-2 text-sm text-amber-800">Эта копия уже отправлена или подписана. Размещение доступно только для просмотра.</p>
        <main class="min-h-0 flex-1 overflow-auto bg-slate-200 p-3 dark:bg-slate-800" aria-label="Предпросмотр PDF">
          <p v-if="loading || pageLoading" role="status" class="py-4 text-center text-sm text-slate-600">Загрузка PDF…</p>
          <div v-if="page && pageUrl" ref="pageElement" class="pdf-page" :style="{ width: `${zoom * 100}%`, maxWidth: `${850 * zoom}px`, aspectRatio: `${page.width_mm} / ${page.height_mm}` }" data-testid="facsimile-page" @click="place">
            <img :src="pageUrl" class="pointer-events-none h-full w-full select-none" :alt="`Страница ${currentPage} PDF`" draggable="false" @load="pageImageLoaded" @error="imageError" />
            <template v-for="kind in kinds" :key="kind">
              <div v-if="placement && placement[kind].page_number === currentPage" class="stamp" :class="{ 'stamp-selected': selected === kind, 'stamp-readonly': !preview?.can_save }" :style="stampStyle(kind)">
                <button class="stamp-image" type="button" :aria-label="`${labels[kind]}: перетащите или используйте стрелки клавиатуры`" :disabled="saving || !preview?.can_save" @focus="selected = kind" @click.stop="selected = kind" @keydown="adjust($event, kind)" @pointerdown="beginGesture($event, kind, 'drag')" @pointermove="moveGesture" @pointerup="endGesture" @pointercancel="endGesture" @lostpointercapture="endGesture">
                  <img :src="assetUrls[kind]" :alt="labels[kind]" class="pointer-events-none h-full w-full select-none" draggable="false" @load="assetLoaded($event, kind)" @error="imageError" />
                </button>
                <button v-if="selected === kind && preview?.can_save" class="stamp-resize" type="button" :aria-label="`Изменить размер: ${labels[kind]}`" :disabled="saving" @click.stop @keydown="adjust($event, kind)" @pointerdown.stop="beginGesture($event, kind, 'resize')" @pointermove="moveGesture" @pointerup="endGesture" @pointercancel="endGesture" @lostpointercapture="endGesture">↘</button>
              </div>
            </template>
          </div>
          <!-- Both images are decoded even when their placements are on other pages. -->
          <div class="hidden" aria-hidden="true"><img v-for="kind in kinds" :key="kind" :src="assetUrls[kind] || undefined" alt="" @load="assetLoaded($event, kind)" @error="imageError" /></div>
        </main>
        <footer class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
          <p class="text-xs text-slate-500">Сохраните размещение, затем проверьте готовый PDF перед отправкой.</p>
          <button class="rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" type="button" :disabled="!canSave" data-testid="save-facsimile" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить PDF с подписью и печатью' }}</button>
        </footer>
      </div>
    </dialog>
  </Teleport>
</template>

<style scoped>
.facsimile-dialog { width: 100vw; height: 100dvh; max-width: 100vw; max-height: 100dvh; margin: 0; padding: 0; border: 0; @apply bg-white text-slate-900 dark:bg-slate-900 dark:text-white; }
.facsimile-dialog::backdrop { background: rgb(15 23 42 / 70%); }
.editor-button { @apply min-h-10 rounded-lg border border-slate-300 px-3 text-sm font-semibold hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:hover:bg-slate-800; }
.editor-selected { @apply border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-900 dark:text-brand-200; }
.pdf-page { position: relative; margin: 0 auto; background: white; box-shadow: 0 2px 12px rgb(0 0 0 / 15%); }
.stamp { position: absolute; }
.stamp-selected { outline: 2px solid #2563eb; }
.stamp-readonly { outline: none; }
.stamp-image { width: 100%; height: 100%; padding: 0; display: block; cursor: grab; touch-action: none; }
.stamp-image:active { cursor: grabbing; }
.stamp-image:focus-visible { outline: 3px solid #2563eb; outline-offset: 3px; }
.stamp-resize { position: absolute; right: -12px; bottom: -12px; width: 28px; height: 28px; border-radius: 6px; color: white; background: #2563eb; cursor: nwse-resize; touch-action: none; }
</style>
