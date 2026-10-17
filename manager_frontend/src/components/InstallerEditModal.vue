<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ManagerStaffResponse } from '../api';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { managerSession } from '../services/manager-session';
import { managerInvitationsApi, teamRoles } from '../services/manager-invitations';
import { getApiErrorMessage } from '../utils/api-errors';
import { useDialogA11y } from '../composables/useDialogA11y';
const props = defineProps<{ modelValue: boolean; staffUser?: ManagerStaffResponse | null }>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; success: [] }>();
const loading = ref(false), error = ref(''), role = ref('manager'), status = ref('active'), canManageWorkerMoney = ref(false), canManageWorkerPay = ref(false), contextInvalid = ref(false);
const context = computed(() => `${managerSession.auth.value?.staff_user_id}:${managerStorefrontSelection.selectedTenantId.value}:${managerStorefrontSelection.selectedSlug.value}`);
let editContext = '';
const canAssignOwner = computed(() => managerSession.auth.value?.role === 'owner');
const ownerProtected = computed(() => !canAssignOwner.value && props.staffUser?.primary_role === 'owner');
const close = () => { if (!loading.value) emit('update:modelValue', false); };
const dialogRef = ref<HTMLElement | null>(null);
useDialogA11y({ open: computed(() => props.modelValue), dialogRef, close });
watch(() => props.modelValue, value => { if (value) { role.value = props.staffUser?.primary_role || 'manager'; status.value = props.staffUser?.status || 'active'; canManageWorkerMoney.value = props.staffUser?.can_manage_worker_money ?? false; canManageWorkerPay.value = props.staffUser?.can_manage_worker_pay ?? false; contextInvalid.value = false; editContext = context.value; error.value = ''; } }, { immediate: true });
watch(context, () => { if (props.modelValue) { contextInvalid.value = true; emit('update:modelValue', false); } });
const submit = async () => {
  if (contextInvalid.value || editContext !== context.value || !props.staffUser || loading.value || ownerProtected.value || (!canAssignOwner.value && role.value === 'owner')) return;
  loading.value = true; error.value = '';
  try {
    await managerInvitationsApi.updateMember(props.staffUser.id, { primary_role: role.value, status: status.value, ...(role.value === 'manager' ? { can_manage_worker_money: canManageWorkerMoney.value, can_manage_worker_pay: canManageWorkerPay.value } : {}) });
    if (editContext !== context.value) return;
    emit('success'); emit('update:modelValue', false);
  } catch (e) { error.value = getApiErrorMessage(e); } finally { loading.value = false; }
};
</script>
<template>
  <Teleport v-if="modelValue" to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" @click.self="close">
      <form ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="member-title" tabindex="-1" class="w-full max-w-md space-y-5 rounded-xl bg-white p-6 shadow-xl dark:bg-slate-800" @submit.prevent="submit">
        <div class="flex items-start justify-between gap-3"><div><h2 id="member-title" class="text-xl font-bold">Доступ сотрудника</h2><p class="mt-1 text-sm text-gray-500">{{ staffUser?.display_name }}</p></div><button type="button" aria-label="Закрыть" :disabled="loading" @click="close">✕</button></div>
        <p class="text-sm text-gray-500">Личные данные, пароль и Telegram сотрудник меняет в своём профиле.</p>
        <p v-if="ownerProtected" class="text-sm text-amber-700">Доступ владельца может изменять только владелец компании.</p>
        <label class="block text-sm font-medium">Роль<select aria-label="Роль" v-model="role" class="mt-1 w-full rounded-lg border p-2.5 dark:bg-slate-900" :disabled="loading || ownerProtected || contextInvalid"><option v-for="(label, value) in teamRoles" :key="value" :value="value" :disabled="value === 'owner' && !canAssignOwner">{{ label }}</option></select></label>
        <label v-if="role === 'manager'" class="flex items-start gap-3 text-sm"><input v-model="canManageWorkerMoney" type="checkbox" class="mt-1 h-4 w-4" :disabled="loading || ownerProtected || contextInvalid" />Принимать деньги от монтажников и исправлять получения</label>
        <label v-if="role === 'manager'" class="flex items-start gap-3 text-sm"><input v-model="canManageWorkerPay" type="checkbox" class="mt-1 h-4 w-4" :disabled="loading || ownerProtected || contextInvalid" />Согласовывать вознаграждения и учитывать выплаты монтажникам</label>
        <label class="block text-sm font-medium">Статус<select aria-label="Статус" v-model="status" class="mt-1 w-full rounded-lg border p-2.5 dark:bg-slate-900" :disabled="loading || ownerProtected || contextInvalid"><option value="active">Активен</option><option value="inactive">В архиве</option></select></label>
        <p v-if="error" role="alert" class="text-sm text-red-600">{{ error }}</p>
        <div class="flex justify-end gap-3"><button type="button" class="rounded-lg border px-4 py-2" :disabled="loading" @click="close">Отмена</button><button type="submit" class="rounded-lg bg-brand-600 px-4 py-2 text-white disabled:opacity-50" :disabled="loading || ownerProtected || contextInvalid">{{ loading ? 'Сохраняем…' : 'Сохранить' }}</button></div>
      </form>
    </div>
  </Teleport>
</template>
