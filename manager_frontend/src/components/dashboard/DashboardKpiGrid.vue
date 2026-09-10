<script setup lang="ts">
import type { DashboardKpis } from '../../client';
import { dashboardKpiOrder } from '../../services/dashboard-overview';
import DashboardKpiCard from './DashboardKpiCard.vue';

const props = defineProps<{ kpis: DashboardKpis }>();
</script>

<template>
  <section class="grid grid-cols-2 gap-3 lg:grid-cols-3">
    <DashboardKpiCard
    v-for="(metric, index) in dashboardKpiOrder"
      :key="metric"
      :metric="metric"
      :kpi="props.kpis[metric]"
      :emphasized="index === 0"
    />
  </section>
</template>
