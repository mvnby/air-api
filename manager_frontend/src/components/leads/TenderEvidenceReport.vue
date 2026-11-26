<script setup lang="ts">
import { computed } from 'vue';
import type { ManagerTenderEvidenceReport, TenderQualificationFact } from '../../client';

const props = defineProps<{
  report: ManagerTenderEvidenceReport;
  canDownload?: boolean;
  downloading?: boolean;
}>();
const emit = defineEmits<{ download: [documentId: string] }>();

const fileStatus: Record<string, string> = {
  complete: 'Прочитан',
  partial: 'Прочитан частично',
  unavailable: 'Недоступен',
  unreadable: 'Не удалось прочитать',
  unsupported: 'Формат не поддерживается',
  oversized: 'Превышен размер',
  timeout: 'Истекло время чтения',
  over_analysis_limit: 'Превышен объём разбора',
};
const labels: Record<TenderQualificationFact['kind'], string> = {
  work_scope: 'Работы',
  execution_address: 'Места выполнения',
  equipment_models: 'Модели оборудования',
  equipment_count: 'Количество',
  maintenance_frequency: 'Периодичность обслуживания',
  maintenance_period: 'Период обслуживания',
  installation_lines: 'Трассы и коммуникации',
  installation_access: 'Доступ на объекте',
  materials: 'Материалы',
  requirements: 'Требования',
  sole_proprietor_eligibility: 'Участие ИП',
  estimated_budget: 'Бюджет',
  offer_price: 'Цена предложения',
  submission_method: 'Способ подачи',
  submission_deadline: 'Срок подачи',
  procedure_type: 'Процедура',
  logistics: 'Доставка',
};
const groupedFindings = computed(() => Object.entries(labels).flatMap(([kind, label]) => {
  const quotes = props.report.findings.flatMap((fact) =>
    fact.kind === kind && fact.evidence ? [fact.evidence] : []
  ) || [];
  return quotes.length ? [{ kind, label, quotes }] : [];
}));
</script>

<template>
  <div class="mt-3 space-y-3">
    <div>
      <p class="font-semibold">
        {{ report.document_coverage_complete ? 'Прочитаны все оригиналы' : 'Чтение оригиналов неполное' }}
      </p>
      <p v-if="report.unselected_count" class="mt-1 text-xs text-slate-500">
        Файлов вне проверки: {{ report.unselected_count }}
      </p>
      <ul class="mt-2 space-y-2 text-xs">
        <li v-for="file in report.documents" :key="file.document_id" class="min-w-0">
          <button
            v-if="canDownload"
            type="button"
            class="break-words text-left font-semibold text-brand-700 underline"
            :disabled="downloading"
            @click="emit('download', file.document_id)"
          >{{ file.filename || 'Оригинал' }}</button>
          <span v-else class="break-words font-semibold">{{ file.filename || 'Оригинал' }}</span>
          <span :class="file.status === 'complete' && file.origin === 'source' ? 'text-slate-500' : 'text-amber-800 dark:text-amber-400'">
            · {{ fileStatus[file.status] || 'Требует проверки' }}
            <template v-if="file.origin === 'saved_original'"> · Сохранённая копия</template>
          </span>
          <p v-for="note in file.diagnostics?.slice(0, 2)" :key="note" class="mt-1 break-words text-slate-500">{{ note }}</p>
          <details v-if="(file.diagnostics?.length || 0) > 2" class="mt-1">
            <summary class="cursor-pointer text-slate-600 dark:text-slate-300">Остальные замечания</summary>
            <ul class="mt-1 space-y-1 text-slate-500">
              <li v-for="(note, index) in file.diagnostics?.slice(2)" :key="index" class="break-words">{{ note }}</li>
            </ul>
          </details>
        </li>
      </ul>
    </div>
    <p v-if="report.analysis_status === 'local_evidence_only'" class="text-xs text-amber-800 dark:text-amber-400">
      ИИ временно недоступен. Показаны требования, найденные в прочитанном тексте.
    </p>
    <ul v-if="groupedFindings.length" class="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-700" aria-label="Цитаты из ТЗ">
      <li v-for="group in groupedFindings" :key="group.kind">
        <details :open="group.kind === 'work_scope' || group.kind === 'execution_address'">
          <summary class="cursor-pointer font-semibold">{{ group.label }}</summary>
          <ul class="mt-2 space-y-2 pl-3">
            <li v-for="(evidence, index) in group.quotes" :key="index" class="border-l border-slate-200 pl-2 dark:border-slate-700">
              <blockquote class="whitespace-pre-line break-words text-xs">{{ evidence.quote }}</blockquote>
              <p class="mt-1 break-words text-xs text-slate-500">{{ [evidence.filename, evidence.location].filter(Boolean).join(' · ') }}</p>
            </li>
          </ul>
        </details>
      </li>
    </ul>
    <p v-else class="text-xs text-slate-500">Подтверждённые требования пока не найдены.</p>
  </div>
</template>
