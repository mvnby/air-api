<script setup lang="ts">
import { computed } from 'vue';
import ManagerStorefrontSwitcher from './ManagerStorefrontSwitcher.vue';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
defineProps<{ collapsed: boolean }>();
const { companies, selectedTenantId, storefronts, selectedSlug, loading, switching, error } = managerStorefrontSelection;
const selectCompany = (event: Event) => { const input = event.target as HTMLSelectElement; const next = Number(input.value); input.value = String(selectedTenantId.value || ''); void managerStorefrontSelection.switchCompany(next); };
const company = computed(() => companies.value.find(item => item.tenant_id === selectedTenantId.value));
</script>
<template>
  <div class="space-y-2">
    <section v-if="companies.length" aria-label="Текущая компания" class="rounded-lg bg-[var(--kitlane-sidebar-hover)] p-2.5 text-[var(--kitlane-sidebar-text)]">
      <label :class="collapsed ? 'md:sr-only' : ''" class="block text-[10px] font-bold uppercase tracking-widest text-[var(--kitlane-sidebar-muted)]" for="manager-company-select">Компания</label>
      <select v-if="companies.length > 1" id="manager-company-select" aria-label="Компания" class="mt-1 w-full min-w-0 rounded border border-[var(--kitlane-sidebar-border)] bg-[var(--kitlane-sidebar)] px-1 py-2 text-xs" :value="selectedTenantId || ''" :disabled="loading || switching" @change="selectCompany">
        <option v-if="!selectedTenantId" value="" disabled>Выберите компанию</option><option v-for="item in companies" :key="item.tenant_id" :value="item.tenant_id">{{ item.display_name }}{{ item.access_kind === 'platform_support' ? ' · поддержка' : '' }}</option>
      </select>
      <div v-else class="mt-1 truncate text-xs font-semibold" :title="company?.display_name">{{ collapsed ? company?.display_name.slice(0, 2) : company?.display_name }}</div>
      <p v-if="company?.access_kind === 'platform_support' && !collapsed" class="mt-1 text-[10px] text-amber-300">Доступ поддержки платформы</p>
    </section>
    <ManagerStorefrontSwitcher :storefronts="storefronts" :selected-slug="selectedSlug" :disabled="loading || switching" :collapsed="collapsed" @select="managerStorefrontSelection.switchTo($event)" />
    <p v-if="error" class="mt-1 px-1 text-xs text-amber-600" role="status">{{ error }}</p>
  </div>
</template>
