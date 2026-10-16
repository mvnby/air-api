<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue';
import OrderResponsibleBadge from './OrderResponsibleBadge.vue';
import { orderResponsibilityApi, type OrderResponsiblePerson, type OrderWithResponsibility } from '../../services/order-responsibility';
import { managerSession } from '../../services/manager-session';
import { managerStorefrontSelection } from '../../services/manager-storefront-selection';
import { getApiErrorMessage } from '../../utils/api-errors';
const props = defineProps<{ order: OrderWithResponsibility; canAssign: boolean; busy: boolean; disabled?: boolean; error?: string; assign: (id: number | null) => Promise<boolean> }>();
const editing = ref(false), loading = ref(false), loadError = ref(''), selected = ref('');
const candidates = ref<OrderResponsiblePerson[]>([]);
const current = computed(() => props.order.responsible_person);
const currentUnavailable = computed(() => current.value && !candidates.value.some(person => person.staff_user_id === current.value?.staff_user_id));
const currentId = computed(() => current.value ? String(current.value.staff_user_id) : '');
const scope = computed(() => `${managerSession.auth.value?.staff_user_id}:${managerSession.auth.value?.tenant_id}:${managerStorefrontSelection.selectedSlug.value}:${props.order.id}`);
let generation = 0;
watch(scope, () => { generation++; editing.value = false; loading.value = false; candidates.value = []; loadError.value = ''; }, { flush: 'sync' });
watch([() => props.order.id, () => props.order.responsible_version], () => { selected.value = currentId.value; }, { immediate: true });
onScopeDispose(() => { generation++; });
const load = async () => {
  if (!props.canAssign || props.busy || props.disabled) return;
  const requested = ++generation;
  editing.value = true; selected.value = currentId.value; loading.value = true; loadError.value = '';
  try {
    const first = await orderResponsibilityApi.candidates(1), people = [...first.items];
    for (let page = 2; people.length < first.total; page++) {
      if (generation !== requested) return;
      const next = await orderResponsibilityApi.candidates(page); if (!next.items.length) break; people.push(...next.items);
    }
    if (generation === requested) candidates.value = people.filter(person => person.is_active);
  } catch (cause) { if (generation === requested) loadError.value = getApiErrorMessage(cause); }
  finally { if (generation === requested) loading.value = false; }
};
const submit = async () => {
  if (!props.canAssign || props.busy || props.disabled || loading.value || loadError.value || selected.value === currentId.value) return;
  const staffId = selected.value ? Number(selected.value) : null;
  if (staffId !== null && !candidates.value.some(person => person.staff_user_id === staffId && person.is_active)) return;
  const requestScope = scope.value;
  if (await props.assign(staffId) && requestScope === scope.value) editing.value = false;
};
</script>
<template>
  <section class="space-y-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900" aria-label="Ответственный за заказ">
    <div class="flex min-w-0 items-start justify-between gap-2"><OrderResponsibleBadge :person="current" /><button v-if="!editing" type="button" class="min-h-9 rounded-lg px-2 text-xs font-semibold text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="!canAssign || busy || disabled" @click="load">Изменить</button></div>
    <p v-if="!canAssign" class="text-xs text-slate-500">Назначение недоступно для текущей учётной записи или режима просмотра.</p>
    <form v-if="editing" class="space-y-2" @submit.prevent="submit">
      <p v-if="loading" role="status" class="text-xs text-slate-500">Загрузка сотрудников…</p>
      <label class="block text-xs font-medium">Ответственный менеджер<select v-model="selected" aria-label="Ответственный менеджер" class="mt-1 min-h-10 w-full rounded-lg border bg-white px-2 py-2 text-sm dark:border-slate-600 dark:bg-slate-950" :disabled="busy || disabled || loading || Boolean(loadError)"><option value="">Не назначен</option><option v-if="currentUnavailable && current" :value="String(current.staff_user_id)" disabled>{{ current.display_name }}{{ current.is_active ? ' · недоступен для назначения' : ' · больше не работает в компании' }}</option><option v-for="person in candidates" :key="person.staff_user_id" :value="String(person.staff_user_id)">{{ person.display_name }}</option></select></label>
      <div class="flex flex-wrap gap-2"><button type="submit" class="min-h-9 rounded-lg bg-brand-600 px-3 text-xs font-semibold text-white disabled:opacity-50" :disabled="busy || disabled || loading || Boolean(loadError) || selected === currentId">{{ busy ? 'Сохраняем…' : 'Сохранить' }}</button><button type="button" class="min-h-9 px-2 text-xs text-slate-500" :disabled="busy" @click="editing = false">Отмена</button></div>
    </form>
    <p v-if="loadError || error" role="alert" class="text-xs text-red-700 dark:text-red-300">{{ loadError || error }} <button v-if="loadError" type="button" class="underline" @click="load">Повторить</button></p>
  </section>
</template>
