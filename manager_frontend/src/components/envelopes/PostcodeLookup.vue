<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue';
import { ManagerService, type PostcodeSuggestion } from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ customerId: number; address: string; disabled?: boolean }>();
const emit = defineEmits<{ selected: [postcode: string] }>();
const expanded = ref(false);
const query = ref(props.address);
const busy = ref(false);
const searched = ref(false);
const error = ref('');
const items = ref<PostcodeSuggestion[]>([]);
let revision = 0;
function reset() { revision++; busy.value = false; searched.value = false; error.value = ''; items.value = []; }
watch(() => props.address, address => { query.value = address; reset(); });
watch(query, reset);
onUnmounted(() => { revision++; });
async function search() {
  if (busy.value || props.disabled || query.value.trim().length < 3) return;
  const current = ++revision;
  busy.value = true; error.value = ''; items.value = []; searched.value = false;
  try {
    const result = await ManagerService.lookupManagerCustomerPostcodes(props.customerId, { address: query.value.trim() });
    if (current === revision) { items.value = result.items; searched.value = true; }
  } catch (e) { if (current === revision) error.value = getApiErrorMessage(e); }
  finally { if (current === revision) busy.value = false; }
}
function choose(code: string) { if (!props.disabled) { emit('selected', code); expanded.value = false; } }
</script>
<template>
  <div class="postcode-lookup">
    <button type="button" class="lookup-toggle" :disabled="disabled" :aria-expanded="expanded" @click="expanded = !expanded">Подобрать индекс по Белпочте</button>
    <div v-if="expanded" class="lookup-panel">
      <label>Населённый пункт и улица<input v-model="query" aria-label="Адрес для поиска индекса" maxlength="600" :disabled="disabled" @keydown.enter.prevent="search" /></label>
      <button type="button" class="btn-mini-outline" :disabled="busy || disabled || query.trim().length < 3" @click="search">{{ busy ? 'Поиск…' : 'Найти индекс' }}</button>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-else-if="searched && !items.length" role="status">Адрес не найден. Уточните населённый пункт и улицу или введите индекс вручную.</p>
      <template v-if="items.length"><p>Выберите совпадающий адрес и проверьте номер дома.</p><ul aria-label="Подсказки Белпочты"><li v-for="(item, index) in items" :key="index"><button type="button" :disabled="disabled" @click="choose(item.postal_code)"><strong>{{ item.postal_code }}</strong><span>{{ item.address }}</span><small v-if="item.buildings">Дома: {{ item.buildings }}</small></button></li></ul></template>
    </div>
    <a href="https://belpost.by/Uznatpochtovyykod28indek" target="_blank" rel="noopener noreferrer">Открыть справочник Белпочты ↗</a>
  </div>
</template>
<style scoped>
.postcode-lookup { font-size: 12px; } .lookup-toggle, a { color: var(--kitlane-accent-text, #2563eb); } a { display: block; margin-top: 6px; } .lookup-panel { margin-top: 8px; padding: 10px; border: 1px solid var(--mv-border, #cbd5e1); border-radius: 8px; } label { display: block; } input { width: 100%; margin: 4px 0 8px; padding: 7px; border: 1px solid var(--mv-border, #cbd5e1); border-radius: 6px; background: var(--mv-surface, white); color: inherit; } p { margin-top: 8px; } ul { max-height: 240px; overflow-y: auto; margin-top: 8px; } li + li { border-top: 1px solid var(--mv-border, #cbd5e1); } li button { display: grid; gap: 3px; width: 100%; text-align: left; padding: 8px 0; } li button:hover { color: var(--kitlane-accent-text, #2563eb); } small { color: var(--mv-text-muted, #64748b); overflow-wrap: anywhere; } button:disabled { opacity: .5; }
</style>
