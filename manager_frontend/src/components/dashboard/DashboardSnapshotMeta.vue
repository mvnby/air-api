<script setup lang="ts">
import { formatDashboardSnapshotPeriod, formatDashboardUpdatedAt } from '../../services/dashboard-overview';

defineProps<{ snapshot: {
  updated_at?: string | null;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  error_code?: string | null;
  period_start?: string | null;
  period_end?: string | null;
} }>();
</script>

<template>
  <div class="mt-3 space-y-1 text-xs text-slate-400 dark:text-[var(--kitlane-muted)]">
    <p v-if="snapshot.period_start && snapshot.period_end">Период снимка: {{ formatDashboardSnapshotPeriod(snapshot.period_start, snapshot.period_end) }}</p>
    <p v-if="snapshot.updated_at">Последнее успешное обновление: {{ formatDashboardUpdatedAt(snapshot.updated_at) }}</p>
    <p v-if="snapshot.error_code" class="text-amber-700 dark:text-amber-300">Не удалось обновить. {{ snapshot.updated_at ? 'Сохранены последние полученные показатели.' : 'Показатели пока недоступны.' }}<span v-if="snapshot.last_attempt_at"> Попытка: {{ formatDashboardUpdatedAt(snapshot.last_attempt_at) }}.</span><span v-if="snapshot.next_retry_at"> Следующая попытка: {{ formatDashboardUpdatedAt(snapshot.next_retry_at) }}.</span></p>
  </div>
</template>
