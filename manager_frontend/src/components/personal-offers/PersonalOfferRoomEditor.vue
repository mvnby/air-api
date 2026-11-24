<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';
import { ChevronDown, ChevronUp, GripVertical, X } from 'lucide-vue-next';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';
import { personalOfferRoomName, type DraftOption, type DraftRoom } from '../../services/personal-offers';
import PersonalOfferOptionFields from './PersonalOfferOptionFields.vue';

const props = defineProps<{
  room: DraftRoom;
  index: number;
  roomNames: string[];
  roomKey: number;
  choices: CatalogDecisionItem[];
  pickerLimit: number;
  addedCount?: number;
}>();
const emit = defineEmits<{
  remove: [];
  pickModels: [event: MouseEvent];
  removeOption: [optionIndex: number];
  moveOption: [optionIndex: number, roomIndex: number];
}>();

const isPackage = computed(() => props.room.selection_mode === 'package');
const titlePlaceholder = computed(() => personalOfferRoomName(props.index, props.roomNames.length, props.room.selection_mode));
const products = computed(() => new Map(props.choices.map(item => [item.id, item])));
const optionTitle = (id: number) => products.value.get(id)?.title || 'Модель #' + id;
const optionKeys = new WeakMap<DraftOption, number>();
let nextOptionKey = 0;
const draggedOption = ref<DraftOption | null>(null);
const dropSlot = ref<number | null>(null);
const reorderStatus = ref('');

function optionKey(option: DraftOption) {
  const key = optionKeys.get(option) ?? nextOptionKey++;
  optionKeys.set(option, key);
  return key;
}

function reorderOption(from: number, to: number) {
  const options = props.room.options;
  const option = options[from];
  if (!option || from === to || to < 0 || to >= options.length) return;
  options.splice(from, 1);
  options.splice(to, 0, option);
  reorderStatus.value = `${optionTitle(option.product_id)}, позиция ${to + 1} из ${options.length}`;
}

async function stepOption(event: MouseEvent, from: number, offset: number) {
  const button = event.currentTarget as HTMLButtonElement;
  const row = button.closest('li');
  reorderOption(from, from + offset);
  await nextTick();
  // Restore focus when the DOM moves the row or disables the button at an edge.
  (button.disabled ? row?.querySelector<HTMLButtonElement>('[data-reorder-step]:not(:disabled)') : button)?.focus();
}

function startDrag(event: DragEvent, option: DraftOption) {
  if (!event.dataTransfer) return;
  draggedOption.value = option;
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', '');
}

function dragOver(event: DragEvent) {
  if (!draggedOption.value || !event.dataTransfer) return;
  event.preventDefault();
  const list = event.currentTarget as HTMLUListElement;
  const nextRow = Array.from(list.children).findIndex(row => {
    const { top, height } = row.getBoundingClientRect();
    return event.clientY < top + height / 2;
  });
  const slot = nextRow < 0 ? props.room.options.length : nextRow;
  const from = props.room.options.indexOf(draggedOption.value);
  const canMove = from >= 0 && slot !== from && slot !== from + 1;
  event.dataTransfer.dropEffect = canMove ? 'move' : 'none';
  dropSlot.value = canMove ? slot : null;
}

function dragLeave(event: DragEvent) {
  const list = event.currentTarget as HTMLUListElement;
  if (event.relatedTarget instanceof Node) {
    if (!list.contains(event.relatedTarget)) dropSlot.value = null;
    return;
  }
  const { top, bottom, left, right } = list.getBoundingClientRect();
  if (event.clientY < top || event.clientY >= bottom || event.clientX < left || event.clientX >= right) {
    dropSlot.value = null;
  }
}

function endDrag() {
  draggedOption.value = null;
  dropSlot.value = null;
}

function dropOption(event: DragEvent) {
  if (!draggedOption.value) return;
  event.preventDefault();
  if (dropSlot.value !== null) {
    const from = props.room.options.indexOf(draggedOption.value);
    const to = dropSlot.value > from ? dropSlot.value - 1 : dropSlot.value;
    reorderOption(from, to);
  }
  endDrag();
}

function moveModel(event: Event, from: number) {
  const select = event.target as HTMLSelectElement;
  if (select.value) emit('moveOption', from, Number(select.value) - 1);
  select.value = '';
}
</script>

<template>
  <section class="space-y-4 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-4" :aria-labelledby="'offer-room-' + roomKey" tabindex="-1">
    <div class="flex flex-wrap items-end justify-between gap-2">
      <label class="min-w-0 flex-1 text-sm font-medium" :id="'offer-room-' + roomKey">
        {{ isPackage ? 'Название комплекта' : 'Название помещения' }}
        <input v-model="room.title" type="text" :placeholder="titlePlaceholder" maxlength="100" class="field-input mt-1 w-full" />
      </label>
      <button v-if="roomNames.length > 1" type="button" class="rounded-lg px-2 py-2 text-sm text-red-700 underline" @click="emit('remove')">{{ isPackage ? 'Убрать комплект' : 'Убрать помещение' }}</button>
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <label class="text-sm font-medium">{{ isPackage ? 'Монтаж всего комплекта' : 'Монтаж' }}
        <select v-model="room.installation.mode" class="field-input mt-1 w-full">
          <option value="none">Только оборудование</option>
          <option value="unknown">Стоимость уточним</option>
          <option value="fixed">Указать стоимость</option>
        </select>
      </label>
      <label v-if="room.installation.mode === 'fixed'" class="text-sm font-medium">Монтаж, BYN
        <input v-model="room.installation.price_byn" type="text" inputmode="decimal" maxlength="14" class="field-input mt-1 w-full" />
      </label>
      <label v-if="room.installation.mode !== 'none'" class="text-sm font-medium sm:col-span-2">Условия монтажа
        <textarea v-model="room.installation.description" rows="2" maxlength="500" class="field-input mt-1 w-full" />
      </label>
    </div>
    <label v-if="isPackage" class="flex items-center gap-2 text-sm font-medium">
      <input v-model="room.show_total" type="checkbox" />
      Показать итог комплекта
    </label>
    <p class="sr-only" role="status">{{ reorderStatus }}</p>
    <ul v-if="room.options.length" class="flex flex-col gap-2" @dragover="dragOver" @dragleave="dragLeave" @drop="dropOption">
      <li
        v-for="(option, optionIndex) in room.options"
        :key="optionKey(option)"
        class="relative grid min-w-0 items-center gap-x-3 gap-y-1 rounded-lg border border-[var(--mv-border)] p-2.5 lg:grid-cols-[auto_minmax(0,1fr)_auto]"
        :class="{
          'insert-before': dropSlot === optionIndex,
          'insert-after': optionIndex === room.options.length - 1 && dropSlot === room.options.length,
        }"
      >
        <span
          v-if="room.options.length > 1"
          class="hidden cursor-grab select-none text-[var(--mv-text-muted)] active:cursor-grabbing lg:col-start-1 lg:row-start-1 lg:block"
          :title="'Перетащить ' + optionTitle(option.product_id)"
          draggable="true"
          @dragstart.stop="startDrag($event, option)"
          @dragend="endDrag"
        >
          <GripVertical class="h-5 w-5" aria-hidden="true" />
        </span>
        <PersonalOfferOptionFields
          :option="option"
          :title="optionTitle(option.product_id)"
          :image="products.get(option.product_id)?.main_image"
          :is-package="isPackage"
        />
        <div class="col-span-full flex flex-wrap items-center gap-1 lg:col-span-1 lg:col-start-3 lg:row-start-1 lg:flex-nowrap lg:justify-end">
          <template v-if="room.options.length > 1">
            <button type="button" data-reorder-step class="order-step w-auto min-w-9 gap-1 px-1.5 text-xs" :aria-label="'Поднять ' + optionTitle(option.product_id)" :disabled="optionIndex === 0" @click="stepOption($event, optionIndex, -1)"><ChevronUp class="h-4 w-4" aria-hidden="true" />Выше</button>
            <button type="button" data-reorder-step class="order-step w-auto min-w-9 gap-1 px-1.5 text-xs" :aria-label="'Опустить ' + optionTitle(option.product_id)" :disabled="optionIndex + 1 === room.options.length" @click="stepOption($event, optionIndex, 1)"><ChevronDown class="h-4 w-4" aria-hidden="true" />Ниже</button>
          </template>
          <select v-if="roomNames.length > 1" class="field-input move-model text-xs" :aria-label="'Перенести ' + optionTitle(option.product_id)" @change="moveModel($event, optionIndex)">
              <option value="">Перенести в…</option>
              <template v-for="(roomName, roomIndex) in roomNames" :key="roomIndex">
                <option v-if="roomIndex !== index" :value="roomIndex + 1">{{ roomName }}</option>
              </template>
          </select>
          <button type="button" class="order-step w-9 text-red-700" :aria-label="'Убрать ' + optionTitle(option.product_id)" title="Убрать модель" @click="emit('removeOption', optionIndex)"><X class="h-4 w-4" aria-hidden="true" /></button>
        </div>
      </li>
    </ul>
    <div class="flex flex-wrap items-center gap-2">
      <button type="button" class="min-h-10 rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm font-semibold disabled:opacity-50" :disabled="pickerLimit <= 0" @click="emit('pickModels', $event)">Добавить из подбора</button>
      <span v-if="pickerLimit <= 0" class="text-sm text-[var(--mv-text-muted)]">Достигнут лимит моделей.</span>
      <span v-if="addedCount" role="status" class="text-sm">Добавлено моделей: {{ addedCount }}</span>
    </div>
  </section>
</template>

<style scoped>
.order-step {
  @apply inline-flex h-9 shrink-0 items-center justify-center rounded-md hover:bg-[var(--kitlane-accent-soft)] disabled:opacity-30;
}

.move-model { width: 8.5rem; }

.insert-before { margin-top: 1rem; }
.insert-after { margin-bottom: 1rem; }

.insert-before::before,
.insert-after::after {
  position: absolute;
  inset-inline: 0;
  height: 2px;
  border-radius: 1px;
  background: var(--kitlane-accent);
  pointer-events: none;
  content: '';
}

.insert-before::before { top: calc(-0.75rem - 1px); }
.insert-before:first-child::before { top: calc(-0.5rem - 1px); }
.insert-after::after { bottom: calc(-0.5rem - 1px); }
</style>
