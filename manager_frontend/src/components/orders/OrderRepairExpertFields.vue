<script setup lang="ts">
import { computed } from 'vue';
import type { RepairMeta } from './repair-meta';

const repairMeta = defineModel<RepairMeta>('repairMeta', { required: true });

const structuredJson = computed(() => JSON.stringify({
  structured_diagnosis: repairMeta.value.structured_diagnosis || {},
  defect_act_blocks: repairMeta.value.defect_act_blocks || {},
  risks: repairMeta.value.risks || [],
  recommended_actions: repairMeta.value.recommended_actions || [],
}, null, 2));
</script>

<template>
  <details class="md:col-span-2 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
    <summary class="cursor-pointer select-none text-sm font-semibold text-amber-900">
      Экспертный режим: JSON и ручные override-поля
    </summary>
    <div class="mt-3 grid gap-3 md:grid-cols-2">
      <label class="field-label md:col-span-2">
        Структурированные выводы AI
        <textarea :value="structuredJson" readonly class="field-input min-h-[180px] font-mono text-xs" />
      </label>
      <label class="field-label">
        Формулировка для акта
        <textarea
          v-model="repairMeta.complaint_official"
          class="field-input min-h-[72px]"
          placeholder="Override официальной формулировки жалобы"
        />
      </label>
      <label class="field-label">
        Вероятный диагноз
        <textarea
          v-model="repairMeta.likely_diagnosis"
          class="field-input min-h-[72px]"
          placeholder="Override предварительной причины"
        />
      </label>
      <label class="field-label">
        Техническое состояние
        <textarea v-model="repairMeta.technical_condition" class="field-input min-h-[80px]" placeholder="Общее состояние, износ, загрязнение, следы вмешательства..." />
      </label>
      <label class="field-label">
        Проверка запуска
        <textarea v-model="repairMeta.startup_check_result" class="field-input min-h-[80px]" placeholder="Запускается / не запускается, ошибки, симптомы..." />
      </label>
      <label class="field-label">
        Проверка компрессора
        <textarea v-model="repairMeta.compressor_check_result" class="field-input min-h-[80px]" placeholder="Токи, сопротивления, срабатывание защиты..." />
      </label>
      <label class="field-label">
        Замеры / диагностика
        <textarea v-model="repairMeta.measurement_result" class="field-input min-h-[80px]" placeholder="Давление, температура, утечки, электрические замеры..." />
      </label>
      <label class="field-label">
        Возможность дальнейшей эксплуатации
        <textarea v-model="repairMeta.further_use_assessment" class="field-input min-h-[80px]" placeholder="Допускается / не допускается / с ограничениями..." />
      </label>
      <label class="field-label">
        Ограничения эксплуатации
        <textarea v-model="repairMeta.operation_restrictions" class="field-input min-h-[80px]" placeholder="Что нельзя делать до ремонта или замены" />
      </label>
      <label class="field-label">
        Целесообразность ремонта
        <textarea v-model="repairMeta.repair_feasibility" class="field-input min-h-[80px]" placeholder="Ремонт целесообразен / нецелесообразен..." />
      </label>
      <label class="field-label">
        Рекомендованное решение
        <textarea v-model="repairMeta.recommended_decision" class="field-input min-h-[80px]" placeholder="Ремонт, замена узла, списание, замена оборудования..." />
      </label>
      <label class="field-label md:col-span-2">
        Техническое заключение
        <textarea v-model="repairMeta.technical_conclusion" class="field-input min-h-[96px]" placeholder="Итоговый вывод для дефектного акта" />
      </label>
    </div>
  </details>
</template>
