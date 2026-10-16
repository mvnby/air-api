<script setup lang="ts">
import { nextTick, onScopeDispose, ref } from 'vue';
import { useDrawerFocusTrap } from '../../composables/useDrawerFocusTrap';
import { FileImage, FileText, Loader2, X } from 'lucide-vue-next';
import { loadInstallerMaterial, type InstallerWorkDetail } from '../../services/installer-workspace';
import { getApiErrorMessage } from '../../utils/api-errors';
defineProps<{ materials: InstallerWorkDetail['materials'] }>();
const preview = ref<{ url: string; label: string; pdf: boolean } | null>(null), busyId = ref<number | null>(null), error = ref('');
const container = ref<HTMLElement | null>(null);
const { captureFocus, focusContainer, restoreFocus, trapFocus } = useDrawerFocusTrap(container);
let generation = 0;
const close = () => { generation++; if (preview.value) URL.revokeObjectURL(preview.value.url); preview.value = null; busyId.value = null; restoreFocus(); };
onScopeDispose(close);
const open = async (material: InstallerWorkDetail['materials'][number]) => {
  close(); captureFocus(); const requested = generation; busyId.value = material.id; error.value = '';
  try { const blob = await loadInstallerMaterial(material.content_url); if (requested !== generation) return; preview.value = { url: URL.createObjectURL(blob), label: material.label, pdf: blob.type === 'application/pdf' }; await nextTick(); if (requested === generation) focusContainer(); }
  catch (cause) { if (requested === generation) error.value = getApiErrorMessage(cause); }
  finally { if (requested === generation) busyId.value = null; }
};
</script>
<template>
  <section v-if="materials.length"><h2 class="mb-3 font-semibold">Материалы по работе</h2><div class="grid gap-2 sm:grid-cols-2"><button v-for="material in materials" :key="material.id" type="button" class="flex min-h-12 items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-left text-sm dark:border-slate-700 dark:bg-slate-900" :disabled="busyId !== null" @click="open(material)"><Loader2 v-if="busyId === material.id" class="h-5 w-5 shrink-0 animate-spin" aria-hidden="true" /><component :is="material.file_kind === 'pdf' ? FileText : FileImage" v-else class="h-5 w-5 shrink-0 text-gray-400" aria-hidden="true" /><span class="break-words">{{ material.label }}</span></button></div><p v-if="error" class="mt-2 text-sm text-red-700" role="alert">{{ error }}</p>
    <Teleport to="body"><div v-if="preview" ref="container" tabindex="-1" @keydown="trapFocus" class="fixed inset-0 z-[200] flex flex-col bg-slate-950/95 p-3 sm:p-6" role="dialog" aria-modal="true" :aria-label="preview.label" @keydown.esc="close"><header class="mb-3 flex items-center justify-between gap-3 text-white"><h3 class="truncate font-medium">{{ preview.label }}</h3><button autofocus type="button" class="rounded-lg p-2 hover:bg-white/10" aria-label="Закрыть материал" @click="close"><X class="h-6 w-6" aria-hidden="true" /></button></header><iframe v-if="preview.pdf" :src="preview.url" :title="preview.label" class="min-h-0 flex-1 rounded-lg bg-white" /><img v-else :src="preview.url" :alt="preview.label" class="min-h-0 flex-1 object-contain" /></div></Teleport>
  </section>
</template>
