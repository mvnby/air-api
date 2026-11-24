<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref, watch } from 'vue';
import PersonalOfferRoomEditor from '../components/personal-offers/PersonalOfferRoomEditor.vue';
import PersonalOfferPreviewPanel from '../components/personal-offers/PersonalOfferPreview.vue';
import CatalogDecisionWorkspaceView from './CatalogDecisionWorkspaceView.vue';
import { catalogDecisionApi, type CatalogDecisionItem } from '../services/catalog-decision-api';
import { readCatalogDecisionQuery, writeCatalogDecisionQuery } from '../services/catalog-decision-query';
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
  type OfferSelectionMode,
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
const editing = Boolean(offerId || selectedIds.length || query.get('new') === '1');
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
const selectionMode = computed(() => rooms.value[0]?.selection_mode ?? 'choice');
const roomNames = computed(() => rooms.value.map((room, index) => room.title?.trim() || personalOfferRoomName(index, rooms.value.length, selectionMode.value)));
const optionCount = computed(() => rooms.value.reduce((count, room) => count + room.options.length, 0));
const picker = ref<{ roomKey: number; title: string; initialSearch: string; existingIds: number[]; limit: number } | null>(null);
const pickerSearches = new Map<number, string>();
const pickerFeedback = ref<{ roomKey: number; count: number } | null>(null);
let pickerTrigger: HTMLButtonElement | null = null;
const returnHref = window.history.state?.managerReturn?.href;
const sourceCatalog = typeof returnHref === 'string' ? new URL(returnHref, window.location.origin) : null;
const catalogSearch = sourceCatalog?.origin === window.location.origin && sourceCatalog.pathname === '/manager/catalog-decision'
  ? sourceCatalog.search
  : '?orderable=1';
let lastPickerSearch = writeCatalogDecisionQuery('', { ...readCatalogDecisionQuery(catalogSearch), page: 1 });
let nextRoomKey = 1;
type OfferAction = 'preview' | 'publish' | 'revoke';
const pendingAction = ref<OfferAction | null>(null);
const busy = computed(() => pendingAction.value !== null);
const actionError = ref<{ action: OfferAction; message: string } | null>(null);
const actionErrorMessage = ref<HTMLElement | null>(null);
const loading = ref(true);
const initialized = ref(false);
const error = ref('');
const status = ref('');
const manualCopy = ref(false);
const linkField = ref<HTMLInputElement | null>(null);
const copyLinkButton = ref<HTMLButtonElement | null>(null);
const previewResult = ref<HTMLElement | null>(null);
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

watch(signature, () => {
  preview.value = null;
  actionError.value = null;
});
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
    } else if (!editing) {
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
  const last = offers.value[offers.value.length - 1];
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

function changeSelectionMode(event: Event) {
  const mode = (event.target as HTMLSelectElement).value as OfferSelectionMode;
  for (const room of rooms.value) {
    room.selection_mode = mode;
    if (mode === 'choice') room.show_total = false;
  }
}

function addRoom() {
  if (rooms.value.length >= 24) return;
  rooms.value.push({ ...newPersonalOfferRoom(), selection_mode: selectionMode.value });
  roomKeys.value.push(nextRoomKey++);
}

function removeRoom(index: number) {
  const removed = rooms.value[index];
  const destination = rooms.value[index === 0 ? 1 : 0];
  if (!removed || !destination) return;
  const remaining = selectionMode.value === 'choice'
    ? removed.options.filter(option => !destination.options.some(item => item.product_id === option.product_id))
    : [];
  if (destination.options.length + remaining.length > 24) {
    error.value = 'Перенесите часть моделей в другие помещения перед удалением.';
    return;
  }
  destination.options.push(...remaining);
  pickerSearches.delete(roomKeys.value[index]!);
  rooms.value.splice(index, 1);
  roomKeys.value.splice(index, 1);
}

const roomPickerLimit = (room: DraftRoom) => Math.min(24 - room.options.length, 48 - optionCount.value);

function openPicker(roomIndex: number, event: MouseEvent) {
  const room = rooms.value[roomIndex];
  if (!room || busy.value || readOnly.value || roomPickerLimit(room) <= 0) return;
  const roomKey = roomKeys.value[roomIndex]!;
  pickerTrigger = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
  pickerFeedback.value = null;
  picker.value = {
    roomKey,
    title: 'Модели · ' + roomNames.value[roomIndex],
    initialSearch: pickerSearches.get(roomKey) ?? lastPickerSearch,
    existingIds: selectionMode.value === 'choice' ? room.options.map(option => option.product_id) : [],
    limit: roomPickerLimit(room),
  };
}

async function closePicker(search: string) {
  if (!picker.value) return;
  pickerSearches.set(picker.value.roomKey, search);
  lastPickerSearch = writeCatalogDecisionQuery('', { ...readCatalogDecisionQuery(search), page: 1 });
  picker.value = null;
  await nextTick();
  revealResult(pickerTrigger?.disabled ? pickerTrigger.closest('section') : pickerTrigger, 'nearest');
  pickerTrigger = null;
}

function addPickedModels(products: CatalogDecisionItem[], search: string) {
  const context = picker.value;
  const room = context && rooms.value[roomKeys.value.indexOf(context.roomKey)];
  if (!context || !room || readOnly.value || busy.value) return;
  const picks = products.filter(item => !context.existingIds.includes(item.id));
  if (picks.length > roomPickerLimit(room)) return;
  error.value = '';
  remember(picks);
  room.options.push(...picks.map(draftOption));
  pickerFeedback.value = { roomKey: context.roomKey, count: picks.length };
  void closePicker(search);
}

function moveOption(roomIndex: number, optionIndex: number, destination: number) {
  const room = rooms.value[roomIndex];
  const option = room?.options[optionIndex];
  const nextRoom = rooms.value[destination];
  if (!room || !option || !nextRoom) return;
  if (nextRoom.options.length >= 24) {
    error.value = 'В группе может быть до 24 моделей.';
    return;
  }
  if (selectionMode.value === 'choice' && nextRoom.options.some(item => item.product_id === option.product_id)) {
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
    const label = title ?? personalOfferRoomName(index, rooms.value.length, selectionMode.value);
    if (!room.options.length) throw new Error(label + ': добавьте хотя бы одну модель.');
    if (selectionMode.value === 'choice' && new Set(room.options.map(option => option.product_id)).size !== room.options.length) {
      throw new Error(label + ': уберите повторяющиеся модели.');
    }
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
      selection_mode: selectionMode.value,
      show_total: selectionMode.value === 'package' && Boolean(room.show_total),
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

function revealResult(element: HTMLElement | null, block: ScrollLogicalPosition) {
  element?.focus({ preventScroll: true });
  element?.scrollIntoView?.({ block, behavior: 'instant' });
}

async function perform(action: OfferAction, run: () => Promise<boolean | void>) {
  if (busy.value || readOnly.value) return false;
  pendingAction.value = action;
  actionError.value = null;
  error.value = '';
  status.value = '';
  try {
    return (await run()) !== false;
  } catch (err) {
    actionError.value = { action, message: getApiErrorMessage(err) };
    await nextTick();
    revealResult(actionErrorMessage.value, 'nearest');
    return false;
  } finally {
    pendingAction.value = null;
  }
}

async function savePreview() {
  if (!await perform('preview', async () => {
    const draft = draftFromForm();
    if (!offer.value || dirty.value) {
      offer.value = offer.value
        ? await personalOffersApi.update(offer.value.id, draft, offer.value.version)
        : await personalOffersApi.create(draft);
      savedForm.value = signature.value;
      if (!offerId) replaceManagerLocation(detailUrl(offer.value.id));
    }
    preview.value = await personalOffersApi.preview(offer.value.id);
  })) return;
  await nextTick();
  revealResult(previewResult.value, 'start');
}

async function publish() {
  if (!preview.value || !offer.value || dirty.value || busy.value) return;
  if (offerActive(offer.value) && !await confirmDialog({
    title: 'Опубликовать новую ссылку?',
    description: 'Предыдущая ссылка перестанет работать.',
    confirmText: 'Опубликовать',
  })) return;
  if (!await perform('publish', async () => {
    if (!offer.value || dirty.value || !preview.value) return false;
    const { id, version } = offer.value;
    if (publicationRequest?.version !== version) publicationRequest = { version, id: crypto.randomUUID() };
    offer.value = await personalOffersApi.publish(id, version, publicationRequest.id);
    publicationRequest = undefined;
    status.value = 'Предложение опубликовано. Ссылку можно отправить клиенту.';
  })) return;
  await nextTick();
  revealResult(copyLinkButton.value, 'center');
}

async function revoke() {
  if (!offer.value?.published || busy.value || !await confirmDialog({
    title: 'Отозвать ссылку?',
    description: 'Клиент больше не сможет открыть предложение по этой ссылке.',
    confirmText: 'Отозвать',
  })) return;
  await perform('revoke', async () => {
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
  <div>
  <CatalogDecisionWorkspaceView v-if="picker" :picker="picker" @pick="addPickedModels" @cancel-pick="closePicker" />
  <section v-show="!picker" class="mx-auto max-w-5xl space-y-4 p-4 sm:p-6" data-testid="personal-offers-workspace">
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
            <p class="mt-1 break-words text-sm text-[var(--mv-text-muted)]">{{ item.rooms.map((room, index) => room.title || personalOfferRoomName(index, item.rooms.length, room.selection_mode)).join(' · ') }}</p>
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
          <button ref="copyLinkButton" type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white" :disabled="!offerActive(offer)" @click="copyLink">Скопировать ссылку</button>
          <button v-if="offerActive(offer) && !readOnly" type="button" class="rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm" :disabled="busy" @click="revoke">Отозвать</button>
        </div>
        <a :href="publicationUrl" target="_blank" rel="noopener noreferrer" class="text-sm underline">Открыть клиентскую страницу</a>
        <p v-if="manualCopy" role="status" class="text-sm">Скопируйте выделенную ссылку вручную.</p>
        <p v-if="actionError?.action === 'revoke'" ref="actionErrorMessage" role="alert" tabindex="-1" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ actionError.message }}</p>
      </section>

      <form class="space-y-4" @submit.prevent="savePreview">
        <fieldset class="space-y-4" :disabled="busy || readOnly">
          <label class="block max-w-sm text-sm font-medium">Действует до
            <input v-model="draftExpiry" type="datetime-local" required class="field-input mt-1 w-full" />
          </label>
          <div>
            <label class="block max-w-sm text-sm font-medium">Как клиент выбирает
              <select :value="selectionMode" class="field-input mt-1 w-full" @change="changeSelectionMode">
                <option value="choice">Подбор по помещениям</option>
                <option value="package">Готовые комплекты</option>
              </select>
            </label>
            <p class="mt-1 text-sm text-[var(--mv-text-muted)]">{{ selectionMode === 'package'
              ? 'Клиент выбирает один комплект целиком. Добавьте в каждый комплект все нужные модели.'
              : 'Клиент выбирает по одной модели для каждого помещения.' }}</p>
          </div>
          <PersonalOfferRoomEditor
            v-for="(room, index) in rooms"
            :key="roomKeys[index]"
            :room="room"
            :room-key="roomKeys[index]!"
            :index="index"
            :room-names="roomNames"
            :choices="choices"
            :picker-limit="roomPickerLimit(room)"
            :added-count="pickerFeedback?.roomKey === roomKeys[index] ? pickerFeedback?.count : undefined"
            @remove="removeRoom(index)"
            @pick-models="openPicker(index, $event)"
            @remove-option="room.options.splice($event, 1)"
            @move-option="(optionIndex, destination) => moveOption(index, optionIndex, destination)"
          />
          <p v-if="actionError?.action === 'preview'" ref="actionErrorMessage" role="alert" tabindex="-1" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ actionError.message }}</p>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm disabled:opacity-50" :disabled="rooms.length >= 24" @click="addRoom">{{ selectionMode === 'package' ? 'Добавить комплект' : 'Добавить помещение' }}</button>
            <button type="submit" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white">{{ pendingAction === 'preview' ? 'Сохраняем…' : 'Сохранить и открыть предпросмотр' }}</button>
          </div>
        </fieldset>
      </form>
      <template v-if="preview">
        <div ref="previewResult" role="group" tabindex="-1" aria-labelledby="offer-preview-heading" class="scroll-mt-24">
          <PersonalOfferPreviewPanel :offer="preview" />
        </div>
        <div class="space-y-2">
          <p v-if="actionError?.action === 'publish'" ref="actionErrorMessage" role="alert" tabindex="-1" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ actionError.message }}</p>
          <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="busy || dirty || readOnly" @click="publish">
            {{ pendingAction === 'publish' ? 'Публикуем…' : offer && offerActive(offer) ? 'Опубликовать новую ссылку' : 'Опубликовать' }}
          </button>
        </div>
      </template>
    </template>
  </section>
  </div>
</template>
