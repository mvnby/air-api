<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronDown, ChevronUp, CircleAlert, LoaderCircle, Pencil, Plus, Power, RefreshCw, ShieldCheck } from 'lucide-vue-next';
import {
  ManagerBrandsService,
  ManagerService,
  ManagerWarrantiesService,
  type ManagerBrandResponse,
  type ManagerWarrantyPolicyPayload,
  type ManagerWarrantyPolicyResponse,
  type SupplierResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import WarrantyPolicyDialog from './WarrantyPolicyDialog.vue';

const expanded = ref(false);
const loaded = ref(false);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const policies = ref<ManagerWarrantyPolicyResponse[]>([]);
const suppliers = ref<SupplierResponse[]>([]);
const brands = ref<ManagerBrandResponse[]>([]);
const editingPolicy = ref<ManagerWarrantyPolicyResponse | null>(null);
const dialogOpen = ref(false);

const activeCount = computed(() => policies.value.filter((item) => item.is_active !== false).length);

const coverageLabel = (value?: string) => value === 'mvn_work' ? 'Работы MVN' : 'Оборудование';
const scopeLabel = (policy: ManagerWarrantyPolicyResponse) => {
  const parts: string[] = [];
  if (policy.product_id) parts.push(policy.product_title || `Товар #${policy.product_id}`);
  else if (policy.series_id) parts.push(policy.series_title || `Серия #${policy.series_id}`);
  else if (policy.brand_id) parts.push(policy.brand_title || `Бренд #${policy.brand_id}`);
  if (policy.supplier_id) parts.push(policy.supplier_name || `Поставщик #${policy.supplier_id}`);
  return parts.join(' · ') || 'Область не указана';
};

const load = async (force = false) => {
  if (loading.value || (loaded.value && !force)) return;
  loading.value = true;
  error.value = '';
  try {
    const [policyResponse, supplierResponse, brandResponse] = await Promise.all([
      ManagerWarrantiesService.listManagerWarrantyPolicies(null, null, null, null, true),
      ManagerService.listSuppliers(),
      ManagerBrandsService.listManagerBrands(),
    ]);
    policies.value = policyResponse.items || [];
    suppliers.value = supplierResponse.items || [];
    brands.value = brandResponse.items || [];
    loaded.value = true;
  } catch (cause) {
    error.value = getApiErrorMessage(cause) || 'Не удалось загрузить правила гарантии';
  } finally {
    loading.value = false;
  }
};

const toggle = () => {
  expanded.value = !expanded.value;
  if (expanded.value) void load();
};

const openCreate = () => {
  editingPolicy.value = null;
  dialogOpen.value = true;
};

const openEdit = (policy: ManagerWarrantyPolicyResponse) => {
  editingPolicy.value = policy;
  dialogOpen.value = true;
};

const save = async (payload: ManagerWarrantyPolicyPayload) => {
  if (saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    if (editingPolicy.value) {
      await ManagerWarrantiesService.patchManagerWarrantyPolicy(editingPolicy.value.id, payload);
    } else {
      await ManagerWarrantiesService.createManagerWarrantyPolicy(payload);
    }
    dialogOpen.value = false;
    editingPolicy.value = null;
    await load(true);
  } catch (cause) {
    error.value = getApiErrorMessage(cause) || 'Не удалось сохранить правило';
  } finally {
    saving.value = false;
  }
};

const toggleActive = async (policy: ManagerWarrantyPolicyResponse) => {
  if (saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    await ManagerWarrantiesService.patchManagerWarrantyPolicy(policy.id, { is_active: policy.is_active === false });
    await load(true);
  } catch (cause) {
    error.value = getApiErrorMessage(cause) || 'Не удалось изменить состояние правила';
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <section class="mb-4 border-y border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900/60">
    <button type="button" class="flex w-full items-center gap-3 px-3 py-3 text-left sm:px-4" :aria-expanded="expanded" @click="toggle">
      <ShieldCheck class="h-5 w-5 shrink-0 text-teal-700 dark:text-teal-300" />
      <span class="min-w-0 flex-1"><span class="block text-sm font-semibold text-slate-900 dark:text-white">Правила гарантии</span><span class="block truncate text-xs text-slate-500 dark:text-slate-400">Условия поставщиков, брендов, серий и товаров</span></span>
      <span v-if="loaded" class="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{{ activeCount }}</span>
      <ChevronUp v-if="expanded" class="h-4 w-4 text-slate-500" /><ChevronDown v-else class="h-4 w-4 text-slate-500" />
    </button>

    <div v-if="expanded" class="border-t border-slate-200 px-3 py-3 dark:border-slate-700 sm:px-4">
      <div class="flex flex-wrap items-center gap-2"><button type="button" class="btn-mini" @click="openCreate"><Plus class="h-4 w-4" />Новое правило</button><button v-if="loaded" type="button" class="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:text-teal-700 dark:border-slate-700 dark:hover:text-teal-300" :disabled="loading" title="Обновить" aria-label="Обновить" @click="load(true)"><RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" /></button></div>
      <div v-if="loading && !loaded" class="flex items-center gap-2 py-6 text-sm text-slate-500"><LoaderCircle class="h-4 w-4 animate-spin" />Загружаем правила</div>
      <p v-if="error && !dialogOpen" class="mt-3 flex items-start gap-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200"><CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />{{ error }}</p>
      <p v-if="loaded && !policies.length" class="py-5 text-center text-sm text-slate-500 dark:text-slate-400">Правил пока нет. Без подходящего правила гарантия будет отмечена как требующая уточнения.</p>
      <div v-else-if="loaded" class="mt-3 divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700">
        <article v-for="policy in policies" :key="policy.id" class="flex items-start gap-3 py-3" :class="policy.is_active === false ? 'opacity-55' : ''">
          <div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2"><h3 class="text-sm font-semibold text-slate-900 dark:text-white">{{ policy.name }}</h3><span class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700 dark:bg-teal-950/40 dark:text-teal-200">{{ coverageLabel(policy.coverage_type) }}</span><span v-if="policy.is_active === false" class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">Отключено</span></div><p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{{ scopeLabel(policy) }} · {{ policy.duration_months || 'срок не задан' }} мес.<span v-if="policy.maintenance_required"> · ТО каждые {{ policy.maintenance_interval_months }} мес.</span></p></div>
          <div class="flex shrink-0 items-center gap-1"><button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-teal-700 dark:hover:bg-slate-800 dark:hover:text-teal-300" title="Изменить" aria-label="Изменить" @click="openEdit(policy)"><Pencil class="h-4 w-4" /></button><button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-teal-700 dark:hover:bg-slate-800 dark:hover:text-teal-300" :title="policy.is_active === false ? 'Включить' : 'Отключить'" :aria-label="policy.is_active === false ? 'Включить' : 'Отключить'" :disabled="saving" @click="toggleActive(policy)"><Power class="h-4 w-4" /></button></div>
        </article>
      </div>
    </div>
  </section>

  <WarrantyPolicyDialog :open="dialogOpen" :policy="editingPolicy" :suppliers="suppliers" :brands="brands" :saving="saving" :error="dialogOpen ? error : ''" @close="dialogOpen = false" @save="save" />
</template>
