<script setup lang="ts">
import { Package } from 'lucide-vue-next';
import type { InstallerEquipment } from '../../services/installer-workspace';
defineProps<{ equipment: InstallerEquipment }>();
</script>
<template>
  <article class="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900" data-testid="installer-equipment">
    <div class="flex items-start gap-3"><Package class="mt-0.5 h-5 w-5 shrink-0 text-gray-400" aria-hidden="true" /><div class="min-w-0"><h3 class="break-words font-semibold text-gray-900 dark:text-white">{{ equipment.name }}</h3><p class="text-sm text-gray-500">{{ [equipment.brand, equipment.model].filter(Boolean).join(' · ') }}<span v-if="equipment.quantity > 1"> · {{ equipment.quantity }} шт.</span></p></div></div>
    <dl class="mt-3 grid gap-2 text-sm"><div v-if="equipment.serial" class="flex justify-between gap-4"><dt class="text-gray-500">Серийный номер</dt><dd class="break-all text-right">{{ equipment.serial }}</dd></div><div v-for="(spec, index) in equipment.technical_specs" :key="index" class="flex justify-between gap-4"><dt class="text-gray-500">{{ spec.label }}</dt><dd class="break-words text-right">{{ spec.value }}</dd></div></dl>
  </article>
</template>
