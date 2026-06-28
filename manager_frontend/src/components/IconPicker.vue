<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

type IconOption = {
    value: string;
    icon: string;
    label: string;
};

const props = withDefaults(defineProps<{
    modelValue: string;
    options: IconOption[];
    tone?: 'indigo' | 'teal';
    label?: string;
}>(), {
    tone: 'indigo',
    label: 'Иконка',
});

const emit = defineEmits<{
    'update:modelValue': [value: string];
}>();

const root = ref<HTMLElement | null>(null);
const isOpen = ref(false);

const selectedOption = computed(() => (
    props.options.find((option) => option.value === (props.modelValue || ''))
    || props.options[0]
    || { value: '', icon: 'hide_image', label: 'Без' }
));

const accentClasses = computed(() => {
    if (props.tone === 'teal') {
        return {
            trigger: 'border-teal-100 bg-teal-50/60 text-teal-800 hover:border-teal-300 dark:border-teal-900/50 dark:bg-teal-950/20 dark:text-teal-100',
            selected: 'border-teal-500 bg-teal-600 text-white shadow-sm',
            idle: 'border-gray-200 bg-white text-gray-600 hover:border-teal-300 hover:text-teal-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-teal-700 dark:hover:text-teal-200',
            icon: 'bg-teal-50 text-teal-700 group-hover:bg-teal-100 dark:bg-slate-800 dark:text-teal-200',
            chip: 'bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-100',
        };
    }
    return {
        trigger: 'border-indigo-100 bg-indigo-50/60 text-indigo-800 hover:border-indigo-300 dark:border-indigo-900/50 dark:bg-indigo-950/20 dark:text-indigo-100',
        selected: 'border-indigo-500 bg-indigo-600 text-white shadow-sm',
        idle: 'border-indigo-100 bg-indigo-50/60 text-gray-600 hover:border-indigo-300 hover:bg-white hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-950/60 dark:text-slate-300 dark:hover:border-indigo-700 dark:hover:bg-slate-900 dark:hover:text-indigo-200',
        icon: 'bg-white text-indigo-700 group-hover:bg-indigo-50 dark:bg-slate-800 dark:text-indigo-200',
        chip: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-100',
    };
});

const choose = (value: string) => {
    emit('update:modelValue', value);
    isOpen.value = false;
};

const onFocusOut = () => {
    window.setTimeout(() => {
        if (!root.value?.contains(document.activeElement)) {
            isOpen.value = false;
        }
    }, 0);
};

const onDocumentPointerDown = (event: PointerEvent) => {
    const target = event.target;
    if (target instanceof Node && !root.value?.contains(target)) {
        isOpen.value = false;
    }
};

onMounted(() => {
    document.addEventListener('pointerdown', onDocumentPointerDown);
});

onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onDocumentPointerDown);
});
</script>

<template>
    <div ref="root" class="relative" @focusin="isOpen = true" @focusout="onFocusOut" @keydown.escape.stop="isOpen = false">
        <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-sm transition"
            :class="accentClasses.trigger"
            :aria-expanded="isOpen"
            @click="isOpen = true"
        >
            <span class="flex min-w-0 items-center gap-2">
                <span class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/70 dark:bg-slate-900/70">
                    <span class="material-icons-round text-[20px]">{{ selectedOption.icon }}</span>
                </span>
                <span class="min-w-0">
                    <span class="block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-400 dark:text-slate-500">{{ label }}</span>
                    <span class="block truncate font-semibold">{{ selectedOption.label }}</span>
                </span>
            </span>
            <span class="inline-flex min-w-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="accentClasses.chip">
                <span class="truncate">{{ modelValue || 'без иконки' }}</span>
                <span class="material-icons-round text-[15px]">expand_more</span>
            </span>
        </button>

        <div
            v-if="isOpen"
            class="absolute left-0 right-0 top-full z-40 mt-2 rounded-xl border border-gray-200 bg-white p-2 shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        >
            <div class="grid grid-cols-4 gap-1.5 sm:grid-cols-6 lg:grid-cols-9">
                <button
                    v-for="option in options"
                    :key="`icon-picker-${option.value || 'none'}`"
                    type="button"
                    class="group flex min-h-[60px] flex-col items-center justify-center gap-1 rounded-lg border px-1.5 py-2 text-center transition"
                    :class="(modelValue || '') === option.value ? accentClasses.selected : accentClasses.idle"
                    :aria-pressed="(modelValue || '') === option.value"
                    :title="option.value ? `${option.label}: ${option.value}` : 'Без иконки'"
                    @click="choose(option.value)"
                >
                    <span
                        class="inline-flex h-8 w-8 items-center justify-center rounded-lg transition"
                        :class="(modelValue || '') === option.value ? 'bg-white/15 text-white' : accentClasses.icon"
                    >
                        <span class="material-icons-round text-[20px]">{{ option.icon }}</span>
                    </span>
                    <span class="max-w-full truncate text-[11px] font-semibold leading-tight">{{ option.label }}</span>
                </button>
            </div>
        </div>
    </div>
</template>
