<script setup lang="ts">
import { ref } from 'vue';
import type { TenderPlace } from '../../client';

defineProps<{ label: string }>();
const places = defineModel<TenderPlace[]>({ required: true });
const regions: Record<TenderPlace['region'], string> = {
  '1': 'Брестская область',
  '2': 'Витебская область',
  '3': 'Гомельская область',
  '4': 'Гродненская область',
  '5': 'Минск',
  '6': 'Минская область',
  '7': 'Могилёвская область',
};
const region = ref<TenderPlace['region'] | ''>('');
const locality = ref('');

function addPlace() {
  if (!region.value || places.value.length >= 30) return;
  const name = locality.value.trim() || null;
  if (places.value.some((place) => place.region === region.value && (place.locality || null) === name)) return;
  places.value = [...places.value, { region: region.value, locality: name }];
  region.value = '';
  locality.value = '';
}
</script>

<template>
  <fieldset class="min-w-0">
    <legend class="text-sm font-semibold">{{ label }}</legend>
    <ul v-if="places.length" class="mt-2 space-y-1 text-sm">
      <li v-for="(place, index) in places" :key="index" class="flex items-baseline gap-2">
        <span>{{ regions[place.region] }}<template v-if="place.locality"> · {{ place.locality }}</template></span>
        <button
          type="button"
          class="text-xs text-brand-700 underline"
          :aria-label="`Убрать ${place.locality || regions[place.region]}`"
          @click="places = places.filter((_, position) => position !== index)"
        >Убрать</button>
      </li>
    </ul>
    <div class="mt-2 flex flex-wrap items-end gap-2">
      <label class="min-w-36 flex-1 text-xs">Регион
        <select v-model="region" class="field-input mt-1">
          <option value="">Выберите</option>
          <option v-for="(name, code) in regions" :key="code" :value="code">{{ name }}</option>
        </select>
      </label>
      <label class="min-w-36 flex-1 text-xs">Город или район
        <input v-model="locality" maxlength="150" class="field-input mt-1" placeholder="Весь регион" />
      </label>
      <button type="button" class="btn-mini-outline" :disabled="!region || places.length >= 30" @click="addPlace">Добавить</button>
    </div>
  </fieldset>
</template>
