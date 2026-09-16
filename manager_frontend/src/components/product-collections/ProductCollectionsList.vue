<script setup lang="ts">
import { computed, ref } from 'vue';
import { Plus, RefreshCw, Search } from 'lucide-vue-next';
import type { ManagerProductCollectionResponse } from '../../client';
import { statusLabel } from './product-collection-workspace';
import { placementLabel } from './product-collection-placements';

const props = defineProps<{ collections: ManagerProductCollectionResponse[]; activeId?: number; loading?: boolean }>();
const emit = defineEmits<{ select: [collection: ManagerProductCollectionResponse]; create: []; refresh: [] }>();
const query = ref('');
const status = ref<'all' | 'draft' | 'published' | 'archived'>('all');
const filtered = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase();
  return props.collections.filter(collection => (status.value === 'all' || collection.status === status.value) && (!needle || `${collection.internal_name} ${collection.public_title} ${(collection.placements || []).map(placementLabel).join(' ')}`.toLocaleLowerCase().includes(needle)));
});
</script>

<template>
  <section class="space-y-3" data-testid="product-collections-list">
    <div class="flex items-center justify-between gap-2">
      <div><h2 class="text-sm font-bold uppercase tracking-wider text-slate-500">Подборки</h2><p class="text-xs text-slate-500">Состав витрины и публикация</p></div>
      <div class="flex gap-1"><button class="icon-button" type="button" title="Обновить" @click="emit('refresh')"><RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" /></button><button class="primary-button h-9 px-3" type="button" @click="emit('create')"><Plus class="h-4 w-4" /> <span class="hidden sm:inline">Создать</span></button></div>
    </div>
    <div class="flex flex-wrap gap-2"><label class="search-field"><Search class="h-4 w-4" /><input v-model="query" placeholder="Название, место показа" /></label><div class="status-filter" aria-label="Статус"><button v-for="entry in [['all', 'Все'], ['published', 'Опубликованы'], ['draft', 'Черновики']] as const" :key="entry[0]" type="button" :class="status === entry[0] ? 'status-filter--active' : ''" @click="status = entry[0]">{{ entry[1] }}</button></div></div>
    <div class="collection-table">
      <button v-for="collection in filtered" :key="collection.id" type="button" class="collection-card text-left" :class="activeId === collection.id ? 'collection-card--active' : ''" @click="emit('select', collection)">
        <img v-if="collection.items?.[0]?.main_image" :src="collection.items[0].main_image || ''" class="collection-image" alt="" /><span v-else class="collection-image collection-image--empty">{{ collection.items?.length || 0 }}</span>
        <span class="min-w-0"><strong class="block break-words text-sm text-slate-950 dark:text-white">{{ collection.internal_name }}</strong><span class="mt-1 block break-words text-xs text-slate-500">{{ collection.public_title }}</span><span class="mt-2 block text-xs text-slate-600 dark:text-slate-300">{{ collection.mode === 'automatic' ? 'По правилам' : `${collection.items?.length || 0} товаров` }}</span></span>
        <span class="placements-cell"><span v-for="placement in (collection.placements || []).slice(0, 2)" :key="placement.id" class="placement-chip">{{ placementLabel(placement) }}</span><span v-if="(collection.placements || []).length > 2" class="placement-chip">ещё {{ (collection.placements || []).length - 2 }}</span><span v-if="!(collection.placements || []).length" class="text-xs text-slate-400">Без размещений</span></span>
        <span class="status-chip shrink-0" :class="`status-chip--${collection.status || 'draft'}`">{{ statusLabel(collection.status) }}</span>
      </button>
      <p v-if="!loading && !filtered.length" class="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">Подборок по этому фильтру нет.</p>
    </div>
  </section>
</template>

<style scoped>
.collection-table { display:grid; gap:8px; }.collection-card { display:grid; grid-template-columns:48px minmax(0,1fr) minmax(180px,.8fr) auto; align-items:center; gap:12px; border:1px solid rgb(226 232 240); border-radius:12px; padding:10px 12px; background:white; transition:border-color .15s,background .15s; }
.collection-image { width:48px; height:48px; border-radius:8px; object-fit:contain; background:rgb(241 245 249); }.collection-image--empty { display:grid; place-items:center; color:rgb(100 116 139); font-size:12px; font-weight:700; }.placements-cell { display:flex; min-width:0; flex-wrap:wrap; gap:4px; }.placement-chip { max-width:170px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; border-radius:999px; background:rgb(241 245 249); padding:3px 7px; font-size:11px; color:rgb(71 85 105); }
.collection-card:hover, .collection-card--active { border-color: rgb(37 99 235); background: rgb(239 246 255); }
.status-chip { border-radius: 999px; padding: 2px 7px; font-size: 11px; font-weight: 700; }.status-chip--published { background: rgb(220 252 231); color: rgb(22 101 52); }.status-chip--draft { background: rgb(254 243 199); color: rgb(146 64 14); }.status-chip--archived { background: rgb(226 232 240); color: rgb(71 85 105); }
.icon-button { display:inline-flex; width:36px; height:36px; align-items:center; justify-content:center; border-radius:8px; }.icon-button:hover { background:rgb(241 245 249); }.primary-button { display:inline-flex; align-items:center; gap:6px; border-radius:8px; background:rgb(37 99 235); color:white; font-weight:700; font-size:13px; }.search-field { display:flex; min-width:min(100%,290px); flex:1; align-items:center; gap:7px; border:1px solid rgb(203 213 225); border-radius:8px; padding:0 10px; }.search-field input { min-width:0; width:100%; height:36px; background:transparent; outline:0; font-size:13px; }.status-filter { display:flex; overflow:auto; border:1px solid rgb(203 213 225); border-radius:8px; }.status-filter button { white-space:nowrap; padding:0 9px; font-size:12px; }.status-filter--active { background:rgb(239 246 255); color:rgb(30 64 175); font-weight:700; }
@media(max-width:640px){.collection-card{grid-template-columns:42px minmax(0,1fr) auto;gap:9px}.collection-image{width:42px;height:42px}.placements-cell{grid-column:2 / -1}.primary-button span{display:inline}.status-chip{align-self:start}}
</style>
