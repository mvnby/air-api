<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import type { TenderModuleSettings, TenderLotMatch, TenderProfilePreview, TenderSearchProfile } from '../../client';
import { tenderModuleApi } from '../../services/tender-module';
import { getApiErrorMessage } from '../../utils/api-errors';
import TenderPlacesEditor from './TenderPlacesEditor.vue';

type Profile = Required<TenderSearchProfile>;
type Direction = Profile['included_directions'][number];
type Activity = Profile['excluded_activities'][number];
const directions: Record<Direction, string> = {
  air_conditioning: 'Кондиционеры',
  ventilation: 'Вентиляция',
  refrigeration: 'Холодильное оборудование',
};
const activities: Record<Activity, string> = {
  maintenance: 'Техобслуживание',
  diagnostics: 'Диагностика',
  repair: 'Ремонт',
  supply: 'Закупка / поставка',
  installation: 'Монтаж',
};

const current = ref<TenderModuleSettings | null>(null);
const profiles = ref<Profile[]>([]);
const selected = ref(0);
const editing = computed(() => profiles.value[selected.value]);
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const success = ref('');
const preview = ref<TenderProfilePreview | null>(null);
const previewing = ref(false);
const previewError = ref('');
const resultLabels: Record<TenderLotMatch['reason'], string> = {
  eligible: 'Подходит',
  excluded_place: 'Исключённое место',
  excluded_direction: 'Исключённое направление',
  excluded_activity: 'Исключённый вид работы',
  different_place: 'География вне профиля',
  different_direction: 'Другое направление',
  different_activity: 'Состав работ вне профиля',
  unconfirmed_place: 'Нужно уточнить место',
  unconfirmed_direction: 'Нужно уточнить направление',
  unconfirmed_activity: 'Нужно уточнить виды работ',
};
const changed = computed(() => JSON.stringify(profiles.value) !== JSON.stringify(
  (current.value?.profiles ?? []).map(normalizeProfile),
));

function normalizeProfile(input: TenderSearchProfile): Profile {
  return {
    name: input.name,
    mode: input.mode ?? 'broad',
    included_places: (input.included_places ?? []).map((item) => ({ ...item })),
    excluded_places: (input.excluded_places ?? []).map((item) => ({ ...item })),
    included_directions: [...(input.included_directions ?? [])],
    excluded_directions: [...(input.excluded_directions ?? [])],
    activity_combinations: (input.activity_combinations ?? []).map((group) => [...group]),
    excluded_activities: [...(input.excluded_activities ?? [])],
  };
}

function applyResult(settings: TenderModuleSettings) {
  current.value = settings;
  profiles.value = (settings.profiles ?? []).map(normalizeProfile);
  selected.value = Math.min(selected.value, Math.max(0, profiles.value.length - 1));
}

async function load() {
  loading.value = true;
  error.value = '';
  try { applyResult(await tenderModuleApi.get()); }
  catch (reason) { error.value = getApiErrorMessage(reason); }
  finally { loading.value = false; }
}

async function save(enabled: boolean, edits: Profile[]) {
  if (!current.value?.entitled || saving.value) return;
  const payload = enabled && !edits.length ? [normalizeProfile({ name: 'Все HVAC' })] : edits;
  saving.value = true;
  error.value = '';
  success.value = '';
  try {
    applyResult(await tenderModuleApi.update({ enabled, version: current.value.version, profiles: payload }));
    success.value = 'Настройки сохранены';
  } catch (reason) {
    error.value = getApiErrorMessage(reason);
  } finally {
    saving.value = false;
  }
}

function toggleModule(event: Event) {
  const checkbox = event.target as HTMLInputElement;
  if (!current.value) return;
  const enabled = checkbox.checked;
  checkbox.checked = current.value.enabled;
  void save(enabled, profiles.value);
}

function addProfile() {
  if (profiles.value.length >= 8) return;
  profiles.value.push(normalizeProfile({ name: '' }));
  selected.value = profiles.value.length - 1;
}

function removeProfile() {
  profiles.value.splice(selected.value, 1);
  selected.value = Math.min(selected.value, Math.max(0, profiles.value.length - 1));
}

async function checkProfile() {
  if (!editing.value || previewing.value) return;
  const snapshot = JSON.stringify(editing.value);
  previewing.value = true;
  preview.value = null;
  previewError.value = '';
  try {
    const result = await tenderModuleApi.preview(JSON.parse(snapshot));
    if (JSON.stringify(editing.value) === snapshot) preview.value = result;
  } catch (reason) {
    if (JSON.stringify(editing.value) === snapshot) previewError.value = getApiErrorMessage(reason);
  } finally {
    previewing.value = false;
  }
}

watch(() => JSON.stringify(editing.value), () => {
  preview.value = null;
  previewError.value = '';
});
onMounted(load);
</script>

<template>
  <section class="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 sm:p-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="text-xl font-bold">Тендеры</h2>
      <label v-if="current?.entitled" class="flex items-center gap-2 text-sm">
        <input type="checkbox" role="switch" aria-label="Тендерный модуль" :checked="current.enabled" :disabled="saving" @change="toggleModule" />
        {{ current.enabled ? 'Подключён' : 'Выключен' }}
      </label>
    </div>
    <p v-if="loading" role="status" class="text-sm text-slate-500">Загружаем настройки тендеров…</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <button v-if="error" type="button" class="btn-mini-outline" :disabled="loading || saving" @click="load">Обновить настройки</button>
    <p v-if="success" role="status" class="text-sm text-green-700 dark:text-green-400">{{ success }}</p>
    <p v-if="current && !current.entitled" class="text-sm text-slate-500">Право на подключение выдаёт владелец платформы.</p>
    <fieldset v-if="current?.entitled" class="min-w-0 space-y-4" :disabled="saving">
      <div class="flex flex-wrap items-end gap-2">
        <label v-if="profiles.length" class="grow text-sm">Профиль поиска
          <select v-model.number="selected" class="field-input mt-1">
            <option v-for="(profile, index) in profiles" :key="index" :value="index">{{ profile.name || 'Новый профиль' }}</option>
          </select>
        </label>
        <button type="button" class="btn-mini-outline" :disabled="profiles.length >= 8" @click="addProfile">Добавить профиль</button>
      </div>
      <template v-if="editing">
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="text-sm">Название<input v-model="editing.name" maxlength="96" class="field-input mt-1" /></label>
          <label class="text-sm">Режим поиска
            <select v-model="editing.mode" class="field-input mt-1">
              <option value="broad">Широкий</option>
              <option value="strict">Узкий</option>
            </select>
          </label>
        </div>
        <div class="grid gap-5 border-t border-slate-200 pt-4 dark:border-slate-800 lg:grid-cols-2">
          <TenderPlacesEditor v-model="editing.included_places" :key="`include-${selected}`" label="Искать в этих местах" />
          <TenderPlacesEditor v-model="editing.excluded_places" :key="`exclude-${selected}`" label="Исключить места" />
        </div>
        <p v-if="!editing.included_places.length" class="text-xs text-slate-500">География поиска — вся Беларусь с учётом исключений.</p>
        <div class="grid gap-4 border-t border-slate-200 pt-4 dark:border-slate-800 sm:grid-cols-2">
          <fieldset class="space-y-1">
            <legend class="text-sm font-semibold">Искать направления</legend>
            <label v-for="(label, key) in directions" :key="key" class="flex gap-2 text-sm">
              <input v-model="editing.included_directions" type="checkbox" :value="key" :disabled="editing.excluded_directions.includes(key)" />{{ label }}
            </label>
            <p v-if="!editing.included_directions.length" class="text-xs text-slate-500">Все направления с учётом исключений.</p>
          </fieldset>
          <fieldset class="space-y-1">
            <legend class="text-sm font-semibold">Исключить направления</legend>
            <label v-for="(label, key) in directions" :key="key" class="flex gap-2 text-sm">
              <input v-model="editing.excluded_directions" type="checkbox" :value="key" :disabled="editing.included_directions.includes(key)" />{{ label }}
            </label>
          </fieldset>
        </div>
        <div class="grid gap-4 border-t border-slate-200 pt-4 dark:border-slate-800 sm:grid-cols-2">
          <fieldset class="space-y-2">
            <legend class="text-sm font-semibold">Виды работ и сочетания</legend>
            <p class="text-xs text-slate-500">Отметьте поставку и монтаж в одном сочетании, если нужны обе работы в одном лоте.</p>
            <fieldset v-for="(group, index) in editing.activity_combinations" :key="index" class="rounded-lg border p-2">
              <p v-if="!group.length" class="text-xs text-slate-500">Выберите виды работ.</p>
              <label v-for="(label, key) in activities" :key="key" class="flex gap-2 text-sm">
                <input v-model="editing.activity_combinations[index]" type="checkbox" :value="key" :disabled="editing.excluded_activities.includes(key)" />{{ label }}
              </label>
              <button type="button" class="mt-1 text-xs text-brand-700 underline" @click="editing.activity_combinations.splice(index, 1)">Убрать сочетание</button>
            </fieldset>
            <button type="button" class="btn-mini-outline" :disabled="editing.activity_combinations.length >= 12" @click="editing.activity_combinations.push([])">Добавить сочетание</button>
          </fieldset>
          <fieldset class="space-y-1">
            <legend class="text-sm font-semibold">Исключить работы</legend>
            <label v-for="(label, key) in activities" :key="key" class="flex gap-2 text-sm">
              <input v-model="editing.excluded_activities" type="checkbox" :value="key" :disabled="editing.activity_combinations.some((group) => group.includes(key))" />{{ label }}
            </label>
          </fieldset>
        </div>
        <button type="button" class="text-sm text-red-700 underline" @click="removeProfile">Убрать профиль</button>
      </template>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn-mini" :disabled="!changed || (current.enabled && !profiles.length)" @click="save(current.enabled, profiles)">Сохранить профили</button>
        <button v-if="editing" type="button" class="btn-mini-outline" :disabled="previewing || !editing.name.trim()" @click="checkProfile">
          {{ previewing ? 'Проверяем…' : 'Проверить на полученных закупках' }}
        </button>
      </div>
      <p v-if="previewError" role="alert" class="text-sm text-red-700">{{ previewError }}</p>
      <template v-if="preview">
        <p v-if="!preview.items.length" class="text-sm text-slate-500">В этой витрине пока нет полученных закупок.</p>
        <ul v-else class="space-y-2 border-t border-slate-200 pt-3 text-sm dark:border-slate-800" aria-label="Предпросмотр профиля">
          <li v-for="item in preview.items" :key="item.order_id" class="flex flex-wrap items-baseline justify-between gap-2">
            <a :href="`/manager/orders/${item.order_id}`" class="break-words text-brand-700 underline">{{ item.title }}</a>
            <span class="text-xs font-semibold" :class="item.result.state === 'review' ? 'text-amber-800 dark:text-amber-400' : 'text-slate-600 dark:text-slate-300'">{{ resultLabels[item.result.reason] }}</span>
          </li>
        </ul>
      </template>
    </fieldset>
  </section>
</template>
