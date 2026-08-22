<script setup lang="ts">
import type { DashboardKpis } from '../../client';
import { dashboardKpiOrder, type DashboardMode } from '../../services/dashboard-overview';
import DashboardKpiCard from './DashboardKpiCard.vue';

const props = defineProps<{ kpis: DashboardKpis; mode: DashboardMode }>();
</script>

<template>
  <section class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
    <DashboardKpiCard
      v-for="(metric, index) in dashboardKpiOrder[props.mode]"
      :key="metric"
      :metric="metric"
      :kpi="props.kpis[metric]"
      :emphasized="(props.mode === 'manager' && index < 2) || (props.mode === 'owner' && index === 0)"
    />
  </section>
</template>
