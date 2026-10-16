<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { managerInvitationsApi, teamRoles, type InviteRole, type TeamInvitation } from '../../services/manager-invitations';
import { managerSession } from '../../services/manager-session';
import { useDemoReadOnly } from '../../services/manager-demo';
import { getApiErrorMessage } from '../../utils/api-errors';
const readonly = useDemoReadOnly();
const canInviteOwner = computed(() => managerSession.auth.value?.role === 'owner');
const role = ref<InviteRole>('manager'), items = ref<TeamInvitation[]>([]), page = ref(1), total = ref(0);
const createdInvitationId = ref<number | null>(null);
const busy = ref(false), rowBusy = ref<number | null>(null), error = ref(''), inviteUrl = ref(''), copied = ref(false);
const date = (value: string) => new Date(value).toLocaleString('ru-RU');
const load = async () => { try { const result = await managerInvitationsApi.list(page.value); items.value = result.items; total.value = result.total; } catch (e) { error.value = getApiErrorMessage(e); } };
const create = async () => {
  if (busy.value || readonly.value || (role.value === 'owner' && !canInviteOwner.value)) return;
  busy.value = true; error.value = ''; inviteUrl.value = ''; copied.value = false;
  try { const result = await managerInvitationsApi.create(role.value); inviteUrl.value = result.invite_url; createdInvitationId.value = result.id; page.value = 1; await load(); }
  catch (e) { error.value = getApiErrorMessage(e); } finally { busy.value = false; }
};
const copy = async () => { try { await navigator.clipboard.writeText(inviteUrl.value); copied.value = true; } catch { error.value = 'Скопируйте ссылку из поля вручную'; } };
const revoke = async (item: TeamInvitation) => {
  if (rowBusy.value || readonly.value) return;
  rowBusy.value = item.id; error.value = '';
  try { await managerInvitationsApi.revoke(item.id); if (createdInvitationId.value === item.id) { inviteUrl.value = ''; createdInvitationId.value = null; } await load(); } catch (e) { error.value = getApiErrorMessage(e); } finally { rowBusy.value = null; }
};
const changePage = (value: number) => { page.value = value; void load(); };
onMounted(load);
</script>
<template>
  <section class="mb-6 space-y-4 rounded-xl border bg-white p-5 dark:border-slate-700 dark:bg-slate-800" aria-labelledby="invitations-heading">
    <div><h2 id="invitations-heading" class="font-semibold">Приглашения в компанию</h2><p class="mt-1 text-sm text-gray-500">Ссылка действует 7 дней. Отправьте её будущему сотруднику лично: он войдёт со своим аккаунтом или создаст новый.</p></div>
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="create"><label class="text-sm font-medium">Роль<select aria-label="Роль приглашения" v-model="role" class="mt-1 block rounded-lg border px-3 py-2 dark:bg-slate-900" :disabled="busy || readonly"><option v-for="(label, value) in teamRoles" :key="value" :value="value" :disabled="value === 'owner' && !canInviteOwner">{{ label }}</option></select></label><button class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" :disabled="busy || readonly">{{ busy ? 'Создаём…' : 'Создать приглашение' }}</button></form>
    <div v-if="inviteUrl" class="rounded-lg bg-blue-50 p-3 dark:bg-slate-900"><label class="block text-sm font-medium">Ссылка приглашения<input :value="inviteUrl" readonly class="mt-2 w-full rounded border bg-white px-3 py-2 text-sm text-gray-900" @focus="($event.target as HTMLInputElement).select()" /></label><button type="button" class="mt-2 text-sm font-semibold text-brand-700" @click="copy">{{ copied ? 'Скопировано' : 'Скопировать ссылку' }}</button></div>
    <p v-if="error" role="alert" class="text-sm text-red-600">{{ error }}</p>
    <ul v-if="items.length" class="divide-y dark:divide-slate-700"><li v-for="item in items" :key="item.id" class="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"><div><span class="font-medium">{{ teamRoles[item.role] }}</span><span class="ml-2 text-gray-500">{{ item.status === 'pending' ? `До ${date(item.expires_at)}` : item.status === 'accepted' ? 'Принято' : item.status === 'revoked' ? 'Отозвано' : item.status === 'expired' ? 'Истекло' : item.status }}</span></div><button v-if="item.status === 'pending'" type="button" class="text-red-600 disabled:opacity-50" :disabled="rowBusy !== null || readonly" @click="revoke(item)">{{ rowBusy === item.id ? 'Отзываем…' : 'Отозвать' }}</button></li></ul>
    <p v-else class="text-sm text-gray-500">Приглашений пока нет.</p>
    <div v-if="total > 50" class="flex items-center justify-end gap-3 text-sm"><button :disabled="page <= 1" @click="changePage(page - 1)">Назад</button><span>Страница {{ page }}</span><button :disabled="page * 50 >= total" @click="changePage(page + 1)">Далее</button></div>
  </section>
</template>
