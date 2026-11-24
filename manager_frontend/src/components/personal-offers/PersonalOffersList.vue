<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { Pencil, Trash2 } from 'lucide-vue-next';
import { navigateManager } from '../../services/manager-navigation-history';
import { personalOfferActive, personalOfferName, personalOfferRoomName, personalOffersApi, type PersonalOffer } from '../../services/personal-offers';
import { confirmDialog, promptDialog } from '../../services/ui-feedback';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{
  orderId?: number;
  detailUrl: (id: number) => string;
  readOnly: boolean;
}>();

const offers = ref<PersonalOffer[]>([]);
const hasMore = ref(false);
const loading = ref(false);
const loaded = ref(false);
const error = ref('');
const status = ref('');

async function load(beforeId?: number) {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  try {
    const result = await personalOffersApi.list(props.orderId, beforeId);
    offers.value = beforeId ? [...offers.value, ...result.items] : result.items;
    hasMore.value = result.has_more;
    loaded.value = true;
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

function loadMore() {
  return load(offers.value[offers.value.length - 1]?.id);
}

async function rename(item: PersonalOffer) {
  if (props.readOnly || loading.value) return;
  await promptDialog({
    title: 'Переименовать предложение',
    inputLabel: 'Название в Manager',
    initialValue: item.title ?? '',
    confirmText: 'Сохранить',
    validate: value => value.length > 100 ? 'Название должно быть не длиннее 100 символов.' : null,
    onConfirm: async value => {
      const renamed = await personalOffersApi.rename(item.id, value || null, item.version);
      offers.value = offers.value.map(row => row.id === renamed.id ? renamed : row);
      status.value = 'Название сохранено.';
    },
    getErrorMessage: getApiErrorMessage,
  });
}

async function remove(item: PersonalOffer) {
  if (props.readOnly || loading.value) return;
  const removed = await confirmDialog({
    title: 'Удалить предложение?',
    description: personalOfferActive(item)
      ? `«${personalOfferName(item)}» исчезнет из списка. Клиентская ссылка перестанет открываться.`
      : `«${personalOfferName(item)}» исчезнет из списка.`,
    confirmText: 'Удалить',
    variant: 'danger',
    onConfirm: async () => {
      await personalOffersApi.delete(item.id, item.version);
      offers.value = offers.value.filter(row => row.id !== item.id);
      status.value = 'Предложение удалено.';
    },
    getErrorMessage: getApiErrorMessage,
  });
  if (removed && !offers.value.length && hasMore.value) await load();
}

onMounted(load);
</script>

<template>
  <div class="space-y-2">
    <p v-if="loading && !loaded" role="status" class="text-sm text-[var(--mv-text-muted)]">Загрузка…</p>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">
      {{ error }}
      <button v-if="!loading" type="button" class="ml-2 underline" @click="loadMore">Повторить</button>
    </p>
    <p v-if="status" role="status" class="text-sm text-[var(--mv-text-muted)]">{{ status }}</p>
    <p v-if="loaded && !loading && !offers.length" class="rounded-lg border border-dashed border-[var(--mv-border)] p-4 text-sm">Здесь будут черновики и опубликованные предложения.</p>
    <ul v-if="offers.length" class="space-y-2">
      <li v-for="item in offers" :key="item.id" class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-3">
        <a :href="detailUrl(item.id)" class="min-w-0 flex-1 rounded break-words focus-visible:outline" @click.prevent="navigateManager(detailUrl(item.id))">
          <strong>{{ personalOfferName(item) }}</strong>
          <span v-if="item.title || item.order_id" class="ml-2 text-xs text-[var(--mv-text-muted)]">
            {{ item.title ? '№' + item.id : '' }}{{ item.title && item.order_id ? ' · ' : '' }}{{ item.order_id ? 'Заказ №' + item.order_id : '' }}
          </span>
          <p class="mt-1 text-sm text-[var(--mv-text-muted)]">{{ item.rooms.map((room, index) => room.title || personalOfferRoomName(index, item.rooms.length, room.selection_mode)).join(' · ') }}</p>
        </a>
        <span class="text-sm text-[var(--mv-text-muted)]">{{ personalOfferActive(item) ? 'Опубликовано' : item.published ? 'Срок истёк' : 'Черновик' }}</span>
        <div v-if="!readOnly" class="flex shrink-0 items-center gap-1">
          <button type="button" title="Переименовать" :aria-label="'Переименовать ' + personalOfferName(item)" class="offer-list-action" :disabled="loading" @click="rename(item)"><Pencil class="size-4" aria-hidden="true" /></button>
          <button type="button" title="Удалить" :aria-label="'Удалить ' + personalOfferName(item)" class="offer-list-action text-red-700" :disabled="loading" @click="remove(item)"><Trash2 class="size-4" aria-hidden="true" /></button>
        </div>
      </li>
    </ul>
    <button v-if="hasMore && offers.length" type="button" class="rounded-lg border border-[var(--mv-border)] px-3 py-2 text-sm" :disabled="loading" @click="loadMore">{{ loading ? 'Загрузка…' : 'Показать ещё' }}</button>
  </div>
</template>

<style scoped>
.offer-list-action {
  @apply inline-flex size-9 items-center justify-center rounded-lg hover:bg-[var(--kitlane-accent-soft)] disabled:opacity-50;
}
</style>
