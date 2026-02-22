<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { ChevronDown, Search } from 'lucide-vue-next';
import { specsTranslations } from '../utils/specsTranslations';

const props = defineProps<{
  modelValue: string;
  knownKeys: string[];
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

const isOpen = ref(false);
const searchQuery = ref('');
const inputRef = ref<HTMLInputElement | null>(null);
const containerRef = ref<HTMLDivElement | null>(null);

// Formatted dictionary for display and searching
const enrichedKeys = computed(() => {
  return props.knownKeys.map(key => {
    const translation = specsTranslations[key];
    return {
      raw: key,
      translation: translation,
      display: translation ? `${translation} [${key}]` : key,
      searchableText: translation ? `${translation.toLowerCase()} ${key.toLowerCase()}` : key.toLowerCase()
    };
  });
});

const filteredOptions = computed(() => {
  const query = searchQuery.value.toLowerCase().trim();
  if (!query) return enrichedKeys.value;
  return enrichedKeys.value.filter(k => k.searchableText.includes(query));
});

// Close when clicking outside
const handleClickOutside = (e: MouseEvent) => {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    isOpen.value = false;
  }
};

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside);
});
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleClickOutside);
});

// Sync local search query with model value if it's set from outside
watch(() => props.modelValue, (newVal) => {
  if (newVal !== searchQuery.value && !isOpen.value) {
    const matched = enrichedKeys.value.find(k => k.raw === newVal);
    searchQuery.value = matched ? matched.display : newVal;
  }
}, { immediate: true });

// Handle inputing new random keys directly
const onInput = (e: Event) => {
  const val = (e.target as HTMLInputElement).value;
  searchQuery.value = val;
  isOpen.value = true;
  // Emit exact raw value typed by the user, assuming it might be a new custom key
  emit('update:modelValue', val);
};

const selectOption = (rawKey: string, display: string) => {
  searchQuery.value = display;
  emit('update:modelValue', rawKey);
  isOpen.value = false;
};

const openDropdown = () => {
  isOpen.value = true;
  // If it's closed and we open it, maybe we want to select all or just show options.
  inputRef.value?.focus();
};

</script>

<template>
  <div class="relative w-full" ref="containerRef">
    <div class="relative flex items-center">
      <Search class="absolute left-3 w-4 h-4 text-gray-400" />
      <input
        ref="inputRef"
        v-model="searchQuery"
        @input="onInput"
        @focus="openDropdown"
        placeholder="Ключ (например: Цвет или color)"
        class="w-full border dark:border-slate-700 bg-white dark:bg-slate-900 dark:text-slate-200 rounded px-9 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
      />
      <button 
        type="button" 
        @click="isOpen = !isOpen" 
        class="absolute right-2 p-1 text-gray-400 hover:text-gray-600 rounded"
      >
        <ChevronDown class="w-4 h-4" :class="{ 'rotate-180': isOpen }" />
      </button>
    </div>

    <!-- Dropdown -->
    <div 
      v-if="isOpen" 
      class="absolute z-50 w-full mt-1 bg-white dark:bg-slate-800 border dark:border-slate-700 rounded-md shadow-lg max-h-[350px] overflow-auto"
    >
      <div v-if="filteredOptions.length === 0" class="p-3 text-sm text-gray-500 text-center">
        Совпадений нет. Будет использован ключ "{{ searchQuery }}"
      </div>
      <ul v-else class="py-1">
        <li 
          v-for="opt in filteredOptions" 
          :key="opt.raw"
          @click="selectOption(opt.raw, opt.display)"
          class="px-3 py-2 text-sm text-gray-700 dark:text-slate-300 hover:bg-teal-50 dark:hover:bg-teal-900/40 cursor-pointer flex flex-col"
        >
          <span v-if="opt.translation" class="font-medium">{{ opt.translation }}</span>
          <span :class="opt.translation ? 'text-xs text-gray-500' : 'font-medium'">{{ opt.raw }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
