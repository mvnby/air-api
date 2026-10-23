<script setup lang="ts">
import type { DashboardKpis } from '../../client';
import { dashboardKpiOrder, type DashboardKpiKey } from '../../services/dashboard-overview';
import DashboardKpiCard from './DashboardKpiCard.vue';

const props = defineProps<{ kpis: DashboardKpis; actionable?: boolean }>();
const emit = defineEmits<{ select: [metric: DashboardKpiKey] }>();
</script>

<template>
  <section class="grid grid-cols-1 min-[390px]:grid-cols-2 gap-3 lg:grid-cols-3">
    <DashboardKpiCard
    v-for="(metric, index) in dashboardKpiOrder"
      :key="metric"
      :metric="metric"
      :kpi="props.kpis[metric]"
      :emphasized="index === 0"
      :actionable="actionable"
      @select="emit('select', $event)"
    />
  </section>
</template>
