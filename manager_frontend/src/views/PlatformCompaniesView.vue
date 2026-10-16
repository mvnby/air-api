<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { registerUnsavedNavigationGuard } from '../services/unsaved-navigation-guard';
import { confirmDialog } from '../services/ui-feedback';
import { managerCompaniesApi, type PlatformCompany } from '../services/manager-companies';
import CompanySitesList from '../components/manager/CompanySitesList.vue';
import { getApiErrorMessage } from '../utils/api-errors';
const items = ref<PlatformCompany[]>([]), total = ref(0), page = ref(1), search = ref(''), loading = ref(false), error = ref('');
const names = ref<Record<number, string>>({}), saving = ref<Record<number, boolean>>({}), errors = ref<Record<number, string>>({});
const unregisterGuard = registerUnsavedNavigationGuard(async () => !items.value.some(item => names.value[item.id] !== item.display_name) || await confirmDialog({ title: 'Покинуть компании?', description: 'Изменения названия ещё не сохранены.', confirmText: 'Покинуть' }));
onBeforeUnmount(unregisterGuard);
let requestId = 0;
const load = async () => { const id = ++requestId; loading.value = true; error.value = ''; try { const result = await managerCompaniesApi.list(page.value, search.value.trim() || undefined); if (id !== requestId) return; items.value = result.items; total.value = result.total; names.value = Object.fromEntries(result.items.map(item => [item.id, item.display_name])); } catch (e) { if (id === requestId) error.value = getApiErrorMessage(e); } finally { if (id === requestId) loading.value = false; } };
const save = async (company: PlatformCompany, changes: { display_name?: string; status?: PlatformCompany['status'] }) => {
  if (saving.value[company.id] || (company.is_system && changes.status && changes.status !== 'active')) return;
  saving.value[company.id] = true; errors.value[company.id] = '';
  try { const updated = await managerCompaniesApi.update(company, changes); items.value = items.value.map(item => item.id === updated.id ? updated : item); names.value[updated.id] = updated.display_name; }
  catch (e) { errors.value[company.id] = getApiErrorMessage(e); } finally { saving.value[company.id] = false; }
};
const toggle = (company: PlatformCompany) => save(company, { status: company.status === 'active' ? 'disabled' : 'active' });
const changePage = (value: number) => { page.value = value; void load(); };
onMounted(load);
</script>
<template>
  <section class="mx-auto max-w-6xl space-y-5 p-4 sm:p-8">
    <div><h1 class="text-2xl font-bold">Компании платформы</h1><p class="mt-1 text-sm text-gray-500">Название, доступ компании и её сайты.</p></div>
    <form class="flex gap-2" @submit.prevent="page = 1; load()"><input v-model="search" aria-label="Поиск компаний" placeholder="Название или адрес компании" class="min-w-0 flex-1 rounded-lg border bg-transparent px-3 py-2" /><button class="rounded-lg bg-brand-600 px-4 py-2 text-white" :disabled="loading">Найти</button></form>
    <p v-if="loading" role="status" class="text-gray-500">Загрузка…</p><p v-if="error" role="alert" class="text-red-600">{{ error }}</p>
    <article v-for="company in items" :key="company.id" class="space-y-4 rounded-xl border bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <div class="flex flex-wrap items-start justify-between gap-4"><div><h2 class="text-lg font-bold">{{ company.display_name }}</h2><p class="mt-1 text-sm text-gray-500">{{ company.slug }} · {{ company.active_staff_count }} сотрудников<span v-if="company.is_system"> · Системная компания</span><span v-if="company.demo_read_only"> · Демонстрационная</span></p><p class="mt-1 text-sm text-gray-500">Владельцы: {{ company.owners.map(owner => owner.display_name).join(', ') || 'Не назначены' }}</p></div>
        <label class="flex items-center gap-2 text-sm"><input type="checkbox" role="switch" :aria-label="`Компания ${company.display_name} активна`" :checked="company.status === 'active'" :disabled="company.is_system || saving[company.id]" @change="toggle(company)" />{{ company.status === 'active' ? 'Активна' : 'Отключена' }}</label>
      </div>
      <form class="flex flex-wrap items-end gap-2" @submit.prevent="save(company, { display_name: names[company.id]?.trim() })"><label class="min-w-0 flex-1 text-sm">Название компании<input v-model="names[company.id]" required maxlength="200" class="mt-1 w-full rounded-lg border bg-transparent px-3 py-2" :disabled="saving[company.id]" /></label><button class="rounded-lg border px-3 py-2 text-sm disabled:opacity-50" :disabled="saving[company.id] || !names[company.id]?.trim() || names[company.id]?.trim() === company.display_name">Сохранить название</button></form>
      <p v-if="company.is_system" class="text-xs text-gray-500">Системную компанию нельзя отключить.</p><p v-if="errors[company.id]" role="alert" class="text-sm text-red-600">{{ errors[company.id] }}</p>
      <CompanySitesList :sites="company.sites" />
    </article>
    <p v-if="!loading && !items.length" class="text-gray-500">Компании не найдены.</p>
    <div v-if="total > 50" class="flex justify-end gap-4 text-sm"><button :disabled="page <= 1 || loading" @click="changePage(page - 1)">Назад</button><span>Страница {{ page }}</span><button :disabled="page * 50 >= total || loading" @click="changePage(page + 1)">Далее</button></div>
  </section>
</template>
