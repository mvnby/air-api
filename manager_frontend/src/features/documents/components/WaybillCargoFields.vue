<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { WaybillCargoLine } from '../../../client';

const lines = defineModel<WaybillCargoLine[]>({ required: true });
const section = ref<HTMLElement | null>(null);
onMounted(() => section.value?.scrollIntoView?.({ block: 'nearest' }));

const update = (index: number, field: 'seats' | 'mass_kg', event: Event) => {
  const input = event.target as HTMLInputElement;
  const value = input.value === '' ? null : field === 'seats' ? input.valueAsNumber : input.value;
  lines.value = lines.value.map((line, i) => i === index ? { ...line, [field]: value } : line);
};
</script>

<template>
  <section ref="section" class="cargo-fields mb-4 min-w-0 space-y-3" data-testid="waybill-cargo">
    <h6 class="text-sm font-bold">Грузовые места и масса</h6>
    <p class="text-xs text-slate-500 dark:text-slate-400">Укажите места и массу всей отгружаемой строки. Неизвестные значения оставьте пустыми.</p>
    <div v-for="(line, index) in lines" :key="line.line_number" class="min-w-0 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      <p class="break-words text-sm font-semibold">{{ line.title }}</p>
      <p class="text-xs text-slate-500">{{ line.quantity }} {{ line.unit }}</p>
      <div class="mt-2 grid min-w-0 gap-2 sm:grid-cols-2">
        <label class="cargo-field"><span>Грузовые места</span>
          <input class="cargo-input" type="number" inputmode="numeric" min="1" max="999999999" step="1" :value="line.seats ?? ''" @input="update(index, 'seats', $event)" />
        </label>
        <label class="cargo-field"><span>Масса, кг</span>
          <input class="cargo-input" type="number" inputmode="decimal" min="0.001" max="999999999.999" step="0.001" :value="line.mass_kg ?? ''" @input="update(index, 'mass_kg', $event)" />
        </label>
      </div>
    </div>
  </section>
</template>

<style scoped>
.cargo-field { @apply flex min-w-0 flex-col gap-1 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.cargo-input { @apply box-border min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-base font-normal text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100; }
@media (max-width: 480px) {
  .cargo-fields { @apply -mx-2; }
}
</style>
