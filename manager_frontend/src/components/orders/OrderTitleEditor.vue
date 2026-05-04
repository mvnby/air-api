<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Check, X } from 'lucide-vue-next';

const props = defineProps<{
  orderId: number;
  title?: string | null;
  fallbackTitle: string;
  textClass?: string;
  inputClass?: string;
}>();

const emit = defineEmits<{
  rename: [payload: { orderId: number; title: string | null }];
}>();

const editing = ref(false);
const draft = ref('');

const savedTitle = computed(() => props.title?.trim() || '');
const displayTitle = computed(() => savedTitle.value || props.fallbackTitle);

watch(
  () => [props.title, props.fallbackTitle],
  () => {
    if (!editing.value) draft.value = savedTitle.value || props.fallbackTitle;
  },
);

const startEditing = () => {
  editing.value = true;
  draft.value = savedTitle.value || props.fallbackTitle;
};

const saveTitle = () => {
  const trimmed = draft.value.trim();
  emit('rename', { orderId: props.orderId, title: trimmed || null });
  editing.value = false;
};

const cancelEditing = () => {
  editing.value = false;
  draft.value = savedTitle.value || props.fallbackTitle;
};
</script>

<template>
  <div class="min-w-0" @click.stop @dblclick.stop>
    <div v-if="editing" class="flex min-w-0 items-center gap-1">
      <input
        v-model="draft"
        class="min-w-0 flex-1 rounded-lg border border-teal-200 bg-white px-2 py-1 text-sm font-semibold text-slate-900 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-white"
        :class="inputClass"
        :placeholder="fallbackTitle"
        autofocus
        @blur="saveTitle"
        @keydown.enter.prevent="saveTitle"
        @keydown.esc.prevent="cancelEditing"
      />
      <button type="button" class="rounded-full p-1 text-teal-700 hover:bg-teal-50 dark:text-teal-300 dark:hover:bg-teal-500/10" @mousedown.prevent @click.stop="saveTitle">
        <Check class="h-3.5 w-3.5" />
      </button>
      <button type="button" class="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-white" @mousedown.prevent @click.stop="cancelEditing">
        <X class="h-3.5 w-3.5" />
      </button>
    </div>
    <p
      v-else
      class="truncate font-semibold text-gray-900 dark:text-white"
      :class="textClass"
      title="Двойной клик — переименовать заказ"
      @dblclick.stop="startEditing"
    >
      {{ displayTitle }}
    </p>
  </div>
</template>
