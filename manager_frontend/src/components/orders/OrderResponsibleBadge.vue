<script setup lang="ts">
import { computed } from 'vue';
import PersonAvatar from '../common/PersonAvatar.vue';
import type { OrderResponsiblePerson } from '../../services/order-responsibility';
const props = defineProps<{ person?: OrderResponsiblePerson | null; interactive?: boolean }>();
const emit = defineEmits<{ open: [] }>();
const label = computed(() => props.person ? `Ответственный: ${props.person.display_name}${props.person.is_active ? '' : ' · больше не работает в компании'}` : 'Ответственный не назначен');
</script>
<template>
  <component :is="interactive ? 'button' : 'div'" :type="interactive ? 'button' : undefined" :title="label" :aria-label="interactive ? `${label}. Открыть заказ` : label" class="inline-flex max-w-full items-center gap-2 rounded-lg text-left text-xs text-slate-600 dark:text-slate-300" :class="interactive ? 'min-h-9 px-1 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800' : ''" @click.stop="interactive && emit('open')" @keydown.stop @pointerdown.stop @dragstart.prevent.stop>
    <PersonAvatar v-if="person" :name="person.display_name" :src="person.avatar_url" size="xs" />
    <span v-else aria-hidden="true" class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800">—</span>
    <span class="min-w-0"><span class="block text-[10px] text-slate-500">Ответственный</span><span class="block truncate font-medium text-slate-800 dark:text-slate-100">{{ person?.display_name || 'Не назначен' }}</span></span>
  </component>
</template>
