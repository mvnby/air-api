<script setup lang="ts">
import { computed, ref } from 'vue';
import { useDialogA11y } from '../../composables/useDialogA11y';
const props = defineProps<{ label: string | null; busy: boolean; error: string; stale: boolean }>();
const emit = defineEmits<{ confirm: []; close: []; refresh: [] }>();
const dialogRef = ref<HTMLElement | null>(null), backRef = ref<HTMLElement | null>(null);
useDialogA11y({ open: computed(() => props.label !== null), dialogRef, initialFocusRef: backRef, close: () => { if (!props.busy && !props.error) emit('close'); } });
</script>
<template><Teleport to="body"><section v-if="label !== null" ref="dialogRef" tabindex="-1" role="dialog" aria-modal="true" aria-label="Подтверждение денежной операции" class="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"><div class="w-full max-w-md rounded-2xl bg-white p-5 dark:bg-slate-900"><p class="whitespace-pre-line text-lg font-semibold">{{ label }}</p><p v-if="error" role="alert" class="mt-3 text-sm text-red-700">{{ error }}</p><button type="button" class="mt-4 rounded-lg bg-brand-600 px-4 py-3 text-white disabled:opacity-50" :disabled="busy || stale" @click="emit('confirm')">{{ busy ? 'Сохраняем…' : 'Подтверждаю' }}</button><button v-if="!error" ref="backRef" type="button" class="ml-3 p-3" :disabled="busy" @click="emit('close')">Назад</button><button v-else type="button" class="ml-3 p-3 underline" :disabled="busy" @click="emit('refresh')">Обновить данные</button></div></section></Teleport></template>
