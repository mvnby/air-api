<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { ManagerAccessItem } from '../client';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../manager-capabilities';
import { managerSession } from '../services/manager-session';
import { catalogPermissions, managerAccessApi, toggleCatalogPermission } from '../services/manager-access';
import { getApiErrorMessage } from '../utils/api-errors';

const allowed = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.infrastructureManage));
const items = ref<ManagerAccessItem[]>([]);
const search = ref('');
const page = ref(1);
const pages = ref(1);
const loading = ref(false);
const error = ref('');
const saving = ref<Record<number, boolean>>({});
const rowErrors = ref<Record<number, string>>({});
let requestVersion = 0;
const roleLabels: Record<string, string> = { owner: 'Владелец', admin: 'Администратор', manager: 'Менеджер', catalog_editor: 'Редактор каталога', installer: 'Монтажник' };
const load = async () => {
  if (!allowed.value) return;
  const version = ++requestVersion;
  loading.value = true;
  error.value = '';
  try {
    const result = await managerAccessApi.list(page.value, search.value.trim() || undefined);
    if (version !== requestVersion) return;
    items.value = result.items;
    pages.value = result.meta.pages;
    rowErrors.value = {};
  } catch (cause) {
    if (version === requestVersion) error.value = getApiErrorMessage(cause);
  } finally {
    if (version === requestVersion) loading.value = false;
  }
};
const find = () => { page.value = 1; void load(); };
const changePage = (value: number) => { page.value = value; void load(); };
const toggle = async (item: ManagerAccessItem, permission: 'edit' | 'delete', event: Event) => {
  const input = event.target as HTMLInputElement;
  const enabled = input.checked;
  input.checked = item.permissions.includes(catalogPermissions[permission]);
  if (!allowed.value || saving.value[item.membership_id]) return;
  saving.value[item.membership_id] = true;
  rowErrors.value[item.membership_id] = '';
  try {
    const updated = await managerAccessApi.update(item, toggleCatalogPermission(item.permissions, permission, enabled));
    const index = items.value.findIndex(row => row.membership_id === item.membership_id);
    if (index >= 0) items.value[index] = updated;
  } catch (cause) {
    rowErrors.value[item.membership_id] = getApiErrorMessage(cause);
  } finally {
    saving.value[item.membership_id] = false;
  }
};
onMounted(load);
</script>

<template>
  <div v-if="allowed" class="mx-auto max-w-6xl space-y-5 p-4 sm:p-6">
    <header>
      <h1 class="text-2xl font-bold text-gray-950 dark:text-white">Доступ к общему каталогу</h1>
      <p class="mt-2 max-w-3xl text-sm text-gray-600 dark:text-slate-300">Права действуют на общий каталог всех компаний. Редактирование открывает карточки, бренды, серии, характеристики и теги. Удаление разрешает удалять и архивировать записи.</p>
    </header>
    <form class="flex gap-2" @submit.prevent="find">
      <input v-model="search" type="search" aria-label="Сотрудник или компания" placeholder="Сотрудник или компания" class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900" />
      <button type="submit" :disabled="loading" class="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white disabled:opacity-50">Найти</button>
    </form>
    <p v-if="error" role="alert" class="text-sm text-red-700 dark:text-red-300">{{ error }} <button type="button" class="underline" @click="load">Повторить</button></p>
    <p v-if="loading" role="status" class="text-sm text-gray-500">Загрузка сотрудников…</p>
    <div v-else class="overflow-x-auto rounded-xl border border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <table class="block w-full text-left text-sm sm:table">
        <thead class="hidden bg-gray-50 sm:table-header-group text-gray-600 dark:bg-slate-800 dark:text-slate-300"><tr><th class="p-4">Сотрудник и компания</th><th class="p-4">Роль</th><th class="p-4">Редактирование</th><th class="p-4">Удаление</th></tr></thead>
        <tbody class="block divide-y sm:table-row-group divide-gray-100 dark:divide-slate-800">
          <tr v-for="item in items" :key="item.membership_id" :data-membership-id="item.membership_id" class="grid grid-cols-2 sm:table-row">
            <td class="col-span-2 block px-4 pt-4 sm:table-cell sm:p-4"><div class="font-semibold">{{ item.display_name }}</div><div class="mt-1 text-gray-500 dark:text-slate-400">{{ item.tenant_name }} · #{{ item.tenant_id }}</div><p v-if="rowErrors[item.membership_id]" role="alert" class="mt-2 text-red-700 dark:text-red-300">{{ rowErrors[item.membership_id] }}</p><p v-if="saving[item.membership_id]" role="status" class="mt-2 text-gray-500">Сохранение…</p></td>
            <td class="col-span-2 block px-4 pb-3 pt-1 text-gray-600 dark:text-slate-300 sm:table-cell sm:p-4">{{ roleLabels[item.role] || item.role }}<span v-if="item.status !== 'active'" class="mt-1 block text-gray-500">{{ item.status === 'inactive' ? 'В архиве' : 'Заблокирован' }}</span></td>
            <td v-for="permission in (['edit', 'delete'] as const)" :key="permission" class="block px-4 pb-4 sm:table-cell sm:p-4"><label class="inline-flex cursor-pointer items-center gap-2"><span class="text-xs font-medium sm:hidden">{{ permission === 'edit' ? 'Редактировать' : 'Удалять' }}</span><input type="checkbox" role="switch" :aria-label="`${permission === 'edit' ? 'Редактирование' : 'Удаление'}: ${item.display_name}, ${item.tenant_name}`" :checked="item.permissions.includes(catalogPermissions[permission])" :disabled="saving[item.membership_id]" class="h-5 w-5 cursor-pointer accent-brand-600 disabled:cursor-wait" @change="toggle(item, permission, $event)" /></label></td>
          </tr>
          <tr v-if="!items.length"><td colspan="4" class="col-span-2 p-8 text-center text-gray-500">Сотрудники не найдены</td></tr>
        </tbody>
      </table>
    </div>
    <nav v-if="pages > 1" aria-label="Страницы сотрудников" class="flex items-center justify-end gap-3 text-sm"><button type="button" :disabled="loading || page <= 1" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="changePage(page - 1)">Назад</button><span>{{ page }} / {{ pages }}</span><button type="button" :disabled="loading || page >= pages" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="changePage(page + 1)">Далее</button></nav>
  </div>
  <p v-else role="alert" class="p-6 text-sm text-gray-600">Управление доступом доступно владельцу платформы.</p>
</template>
