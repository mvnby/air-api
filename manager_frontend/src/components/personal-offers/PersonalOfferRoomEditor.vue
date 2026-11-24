<script setup lang="ts">
import { computed } from 'vue';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';
import { personalOfferRoomName, type DraftRoom } from '../../services/personal-offers';

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
const optionTitle = (id: number) => props.choices.find(choice => choice.id === id)?.title || 'Модель #' + id;

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
    <ul v-if="room.options.length" class="space-y-2">
      <li v-for="(option, optionIndex) in room.options" :key="optionIndex" class="space-y-2 rounded-lg border border-[var(--mv-border)] p-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="min-w-0 break-words text-sm font-semibold">{{ optionTitle(option.product_id) }}</p>
          <div class="flex flex-wrap items-center gap-2">
            <select v-if="roomNames.length > 1" class="field-input text-xs" :aria-label="'Перенести ' + optionTitle(option.product_id)" @change="moveModel($event, optionIndex)">
              <option value="">Перенести в…</option>
              <template v-for="(roomName, roomIndex) in roomNames" :key="roomIndex">
                <option v-if="roomIndex !== index" :value="roomIndex + 1">{{ roomName }}</option>
              </template>
            </select>
            <button type="button" class="text-xs text-red-700 underline" :aria-label="'Убрать ' + optionTitle(option.product_id)" @click="emit('removeOption', optionIndex)">Убрать</button>
          </div>
        </div>
        <div class="grid gap-2 sm:grid-cols-[10rem_1fr]">
          <label class="text-sm font-medium">Цена, BYN
            <input v-model="option.price_byn" type="text" inputmode="decimal" maxlength="14" class="field-input mt-1 w-full" />
          </label>
          <label class="text-sm font-medium">{{ isPackage ? 'Помещение или пояснение для клиента' : 'Пояснение для клиента' }}
            <textarea v-model="option.note" rows="2" maxlength="500" class="field-input mt-1 w-full" />
          </label>
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
