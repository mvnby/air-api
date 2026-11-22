<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue';
import PersonalOfferRoomEditor from '../components/personal-offers/PersonalOfferRoomEditor.vue';
import PersonalOfferPreviewPanel from '../components/personal-offers/PersonalOfferPreview.vue';
import { catalogDecisionApi, type CatalogDecisionItem } from '../services/catalog-decision-api';
import { navigateManager, replaceManagerLocation } from '../services/manager-navigation-history';
import { managerSession } from '../services/manager-session';
import {
  formatOfferDate,
  localOfferDate,
  newPersonalOfferRoom,
  personalOfferMoney,
  personalOfferRoomName,
  personalOffersApi,
  personalOffersPath,
  positiveId,
  type Draft,
  type DraftRoom,
  type PersonalOffer,
  type PersonalOfferPreview,
} from '../services/personal-offers';
import { registerUnsavedNavigationGuard } from '../services/unsaved-navigation-guard';
import { confirmDialog } from '../services/ui-feedback';
import { getApiErrorMessage } from '../utils/api-errors';

const query = new URLSearchParams(window.location.search);
const orderId = positiveId(query.get('orderId'));
const offerId = positiveId(query.get('offerId'));
const selectedIds = [...new Set((query.get('products') ?? '').split(',').flatMap(item => positiveId(item) ?? []))].slice(0, 24);
const editing = Boolean(offerId || selectedIds.length);
const readOnly = computed(() => Boolean(managerSession.auth.value?.demo_read_only));
const offers = ref<PersonalOffer[]>([]);
const hasMore = ref(false);
const loadingMore = ref(false);
const offer = ref<PersonalOffer | null>(null);
const preview = ref<PersonalOfferPreview | null>(null);
const rooms = ref<DraftRoom[]>([newPersonalOfferRoom()]);
const draftExpiry = ref(localOfferDate(new Date(Date.now() + 7 * 86_400_000)));
const choices = ref<CatalogDecisionItem[]>([]);
const roomKeys = ref([0]);
const roomNames = computed(() => rooms.value.map((room, index) => room.title?.trim() || personalOfferRoomName(index, rooms.value.length)));
const optionCount = computed(() => rooms.value.reduce((count, room) => count + room.options.length, 0));
let nextRoomKey = 1;
const busy = ref(false);
const loading = ref(true);
const initialized = ref(false);
const searching = ref(false);
const error = ref('');
const searchStatus = ref('');
const status = ref('');
const manualCopy = ref(false);
const linkField = ref<HTMLInputElement | null>(null);
const savedForm = ref('');
const signature = computed(() => JSON.stringify([rooms.value, draftExpiry.value]));
const dirty = computed(() => editing && !readOnly.value && initialized.value && signature.value !== savedForm.value);
let publicationRequest: { version: number; id: string } | undefined;

onScopeDispose(registerUnsavedNavigationGuard(async () => !busy.value && (!dirty.value || await confirmDialog({
  title: 'Покинуть предложение?',
  description: 'Изменения в черновике ещё не сохранены.',
  confirmText: 'Покинуть',
}))));

const currentOrderId = computed(() => offer.value?.order_id ?? orderId);
const listUrl = orderId ? personalOffersPath + '?orderId=' + orderId : personalOffersPath;
const detailUrl = (id: number) => listUrl + (orderId ? '&' : '?') + 'offerId=' + id;
const publicationUrl = computed(() => offer.value?.published?.url ?? '');
const offerActive = (item: PersonalOffer) =>
  Boolean(item.published && new Date(item.published.expires_at).getTime() > Date.now());

watch(signature, () => { preview.value = null; });
watch(publicationUrl, () => { manualCopy.value = false; });

const remember = (items: CatalogDecisionItem[]) => {
  choices.value = [...new Map([...choices.value, ...items].map(item => [item.id, item])).values()];
};

async function getProducts(ids: number[]) {
  const unique = [...new Set(ids)];
  for (let index = 0; index < unique.length; index += 24) {
    const result = await catalogDecisionApi.list(1, 24, {
      productIds: unique.slice(index, index + 24), includeOrderable: true, isPublished: true,
    }, 'title', 'asc');
    remember(result.items ?? []);
  }
}

const draftOption = (item: CatalogDecisionItem) => ({ product_id: item.id, price_byn: String(item.retail_price_byn), note: null });

async function load() {
  error.value = '';
  loading.value = true;
  try {
    if (offerId) {
      offer.value = await personalOffersApi.get(offerId);
      rooms.value = offer.value.rooms;
      roomKeys.value = rooms.value.map(() => nextRoomKey++);
      draftExpiry.value = localOfferDate(new Date(offer.value.expires_at));
      await getProducts(rooms.value.flatMap(room => room.options.map(option => option.product_id)));
    } else if (selectedIds.length) {
      await getProducts(selectedIds);
      const room = newPersonalOfferRoom();
      room.options = selectedIds.flatMap(id => {
        const product = choices.value.find(item => item.id === id);
        return product ? [draftOption(product)] : [];
      });
      rooms.value = [room];
      if (room.options.length !== selectedIds.length) status.value = 'Часть выбранных моделей больше недоступна в подборе.';
    } else {
      const result = await personalOffersApi.list(orderId);
      offers.value = result.items;
      hasMore.value = result.has_more;
    }
    savedForm.value = signature.value;
    initialized.value = true;
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  const last = offers.value.at(-1);
  if (!last || loadingMore.value) return;
  loadingMore.value = true;
  error.value = '';
  try {
    const result = await personalOffersApi.list(orderId, last.id);
    offers.value.push(...result.items);
    hasMore.value = result.has_more;
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loadingMore.value = false;
  }
}

async function searchModels(search: string) {
  if (!search.trim() || searching.value) return;
  searching.value = true;
  searchStatus.value = 'Ищем модели…';
  try {
    const result = await catalogDecisionApi.list(1, 24, { search: search.trim(), includeOrderable: true, isPublished: true }, 'title', 'asc');
    remember(result.items ?? []);
    searchStatus.value = result.items?.length ? 'Найденные модели добавлены в список выбора.' : 'Модели не найдены.';
  } catch (err) {
    searchStatus.value = getApiErrorMessage(err);
  } finally {
    searching.value = false;
  }
}

function addRoom() {
  if (rooms.value.length >= 24) return;
  rooms.value.push(newPersonalOfferRoom());
  roomKeys.value.push(nextRoomKey++);
}

function removeRoom(index: number) {
  const removed = rooms.value[index];
  const destination = rooms.value[index === 0 ? 1 : 0];
  if (!removed || !destination) return;
  const remaining = removed.options.filter(option => !destination.options.some(item => item.product_id === option.product_id));
  if (destination.options.length + remaining.length > 24) {
    error.value = 'Перенесите часть моделей в другие помещения перед удалением.';
    return;
  }
  destination.options.push(...remaining);
  rooms.value.splice(index, 1);
  roomKeys.value.splice(index, 1);
}

function addOption(roomIndex: number, productId: number) {
  const product = choices.value.find(item => item.id === productId);
  const room = rooms.value[roomIndex];
  if (!product || !room || room.options.some(option => option.product_id === productId)) return;
  if (room.options.length >= 24 || optionCount.value >= 48) {
    error.value = 'Можно добавить до 24 вариантов в помещение и до 48 в предложение.';
    return;
  }
  error.value = '';
  room.options.push(draftOption(product));
}

function moveOption(roomIndex: number, optionIndex: number, destination: number) {
  const room = rooms.value[roomIndex];
  const option = room?.options[optionIndex];
  const nextRoom = rooms.value[destination];
  if (!room || !option || !nextRoom) return;
  if (nextRoom.options.length >= 24) {
    error.value = 'В помещении может быть до 24 вариантов.';
    return;
  }
  if (nextRoom.options.some(item => item.product_id === option.product_id)) {
    error.value = 'В этом помещении уже есть такая модель.';
    return;
  }
  error.value = '';
  nextRoom.options.push(option);
  room.options.splice(optionIndex, 1);
}

function draftFromForm(): Draft {
  const expiry = new Date(draftExpiry.value);
  if (!Number.isFinite(expiry.getTime()) || expiry.getTime() <= Date.now()) throw new Error('Укажите будущую дату окончания предложения.');
  const normalizedRooms = rooms.value.map((room, index) => {
    const title = room.title?.trim() || null;
    const label = title ?? personalOfferRoomName(index, rooms.value.length);
    if (!room.options.length) throw new Error(label + ': добавьте хотя бы одну модель.');
    const fixed = room.installation.mode === 'fixed';
    const installationPrice = fixed ? personalOfferMoney(room.installation.price_byn) : null;
    if (fixed && installationPrice === null) throw new Error(label + ': укажите цену монтажа в BYN.');
    const options = room.options.map(option => {
      const price = personalOfferMoney(option.price_byn);
      if (price === null || Number(price) <= 0) throw new Error(label + ': укажите цену каждой модели в BYN.');
      return { ...option, price_byn: price, note: option.note?.trim() || null };
    });
    return {
      title,
      installation: {
        mode: room.installation.mode,
        price_byn: installationPrice,
        description: room.installation.mode === 'none' ? null : room.installation.description?.trim() || null,
      },
      options,
    };
  });
  return { order_id: currentOrderId.value ?? null, expires_at: expiry.toISOString(), rooms: normalizedRooms };
}

async function perform(action: () => Promise<void>) {
  if (busy.value || readOnly.value) return;
  busy.value = true;
  error.value = '';
  status.value = '';
  try { await action(); }
  catch (err) { error.value = getApiErrorMessage(err); }
  finally { busy.value = false; }
}

async function savePreview() {
  await perform(async () => {
    const draft = draftFromForm();
    if (!offer.value || dirty.value) {
      offer.value = offer.value
        ? await personalOffersApi.update(offer.value.id, draft, offer.value.version)
        : await personalOffersApi.create(draft);
      savedForm.value = signature.value;
      if (!offerId) replaceManagerLocation(detailUrl(offer.value.id));
    }
    preview.value = await personalOffersApi.preview(offer.value.id);
  });
}

async function publish() {
  if (!preview.value || !offer.value || dirty.value || busy.value) return;
  if (offerActive(offer.value) && !await confirmDialog({
    title: 'Опубликовать новую ссылку?',
    description: 'Предыдущая ссылка перестанет работать.',
    confirmText: 'Опубликовать',
  })) return;
  await perform(async () => {
    if (!offer.value || dirty.value || !preview.value) return;
    const { id, version } = offer.value;
    if (publicationRequest?.version !== version) publicationRequest = { version, id: crypto.randomUUID() };
    offer.value = await personalOffersApi.publish(id, version, publicationRequest.id);
    publicationRequest = undefined;
    status.value = 'Предложение опубликовано. Ссылку можно отправить клиенту.';
  });
}

async function revoke() {
  if (!offer.value?.published || busy.value || !await confirmDialog({
    title: 'Отозвать ссылку?',
    description: 'Клиент больше не сможет открыть предложение по этой ссылке.',
    confirmText: 'Отозвать',
  })) return;
  await perform(async () => {
    if (!offer.value) return;
    offer.value = await personalOffersApi.revoke(offer.value.id, offer.value.version);
    status.value = 'Ссылка отозвана.';
  });
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(publicationUrl.value);
    manualCopy.value = false;
    status.value = 'Ссылка скопирована.';
  } catch {
    manualCopy.value = true;
    linkField.value?.focus();
    linkField.value?.select();
  }
}

onMounted(load);
</script>

<template>
  <section class="mx-auto max-w-5xl space-y-4 p-4 sm:p-6" data-testid="personal-offers-workspace">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ editing ? 'Персональное предложение' : 'Персональные предложения' }}</h1>
        <a v-if="currentOrderId" :href="'/manager/orders/kanban?orderId=' + currentOrderId" class="text-sm underline">Заказ №{{ currentOrderId }}</a>
      </div>
      <a v-if="editing" :href="listUrl" class="text-sm font-semibold underline" @click.prevent="navigateManager(listUrl)">Все предложения</a>
      <a v-else href="/manager/catalog-decision" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white">Перейти к подбору</a>
    </header>

    <p v-if="loading" role="status" class="text-sm text-[var(--mv-text-muted)]">Загрузка…</p>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">
      {{ error }}
      <button v-if="!initialized && !loading" type="button" class="ml-2 underline" @click="load">Повторить</button>
    </p>
    <p v-if="status" role="status" class="rounded-lg border border-[var(--mv-border)] p-3 text-sm">{{ status }}</p>

    <template v-if="initialized && !editing">
      <p v-if="!offers.length" class="rounded-lg border border-dashed border-[var(--mv-border)] p-4 text-sm">Здесь будут черновики и ссылки. Начните с подбора оборудования.</p>
      <ul v-else class="space-y-2">
        <li v-for="item in offers" :key="item.id" class="rounded-xl border border-[var(--mv-border)] p-3">
          <a :href="detailUrl(item.id)" class="block focus-visible:outline" @click.prevent="navigateManager(detailUrl(item.id))">
            <div class="flex flex-wrap justify-between gap-2">
              <strong>Предложение №{{ item.id }}<span v-if="item.order_id"> · Заказ №{{ item.order_id }}</span></strong>
              <span class="text-sm">{{ offerActive(item) ? 'Опубликовано' : item.published ? 'Срок истёк' : 'Черновик' }}</span>
            </div>
            <p class="mt-1 break-words text-sm text-[var(--mv-text-muted)]">{{ item.rooms.map((room, index) => room.title || personalOfferRoomName(index, item.rooms.length)).join(' · ') }}</p>
          </a>
        </li>
      </ul>
      <button v-if="hasMore" type="button" class="rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm" :disabled="loadingMore" @click="loadMore">{{ loadingMore ? 'Загрузка…' : 'Показать ещё' }}</button>
    </template>

    <template v-else-if="initialized && editing">
      <section v-if="offer?.published && publicationUrl" class="space-y-2 rounded-xl border border-[var(--mv-border)] p-4">
        <h2 class="text-base font-bold">Опубликованная ссылка</h2>
        <p class="text-sm">{{ offerActive(offer) ? 'Действует до' : 'Срок истёк' }} {{ formatOfferDate(offer.published.expires_at) }}</p>
        <div class="flex flex-wrap gap-2">
          <input ref="linkField" readonly :value="publicationUrl" aria-label="Ссылка на предложение" class="field-input min-w-0 flex-1" @focus="($event.target as HTMLInputElement).select()" />
          <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white" :disabled="!offerActive(offer)" @click="copyLink">Скопировать ссылку</button>
          <button v-if="offerActive(offer) && !readOnly" type="button" class="rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm" :disabled="busy" @click="revoke">Отозвать</button>
        </div>
        <a :href="publicationUrl" target="_blank" rel="noopener noreferrer" class="text-sm underline">Открыть клиентскую страницу</a>
        <p v-if="manualCopy" role="status" class="text-sm">Скопируйте выделенную ссылку вручную.</p>
      </section>

      <form class="space-y-4" @submit.prevent="savePreview">
        <fieldset class="space-y-4" :disabled="busy || readOnly">
          <label class="block max-w-sm text-sm font-medium">Действует до
            <input v-model="draftExpiry" type="datetime-local" required class="field-input mt-1 w-full" />
          </label>
          <PersonalOfferRoomEditor
            v-for="(room, index) in rooms"
            :key="roomKeys[index]"
            :room="room"
            :room-key="roomKeys[index]!"
            :index="index"
            :room-names="roomNames"
            :choices="choices"
            @remove="removeRoom(index)"
            @add-option="addOption(index, $event)"
            @remove-option="room.options.splice($event, 1)"
            @move-option="(optionIndex, destination) => moveOption(index, optionIndex, destination)"
            @search="searchModels"
          />
          <p v-if="searchStatus" role="status" class="text-sm">{{ searchStatus }}</p>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm disabled:opacity-50" :disabled="rooms.length >= 24" @click="addRoom">Добавить помещение</button>
            <button type="submit" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white">{{ busy ? 'Сохраняем…' : 'Сохранить и открыть предпросмотр' }}</button>
          </div>
        </fieldset>
      </form>
      <template v-if="preview">
        <PersonalOfferPreviewPanel :offer="preview" />
        <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="busy || dirty || readOnly" @click="publish">{{ offer && offerActive(offer) ? 'Опубликовать новую ссылку' : 'Опубликовать' }}</button>
      </template>
    </template>
  </section>
</template>
