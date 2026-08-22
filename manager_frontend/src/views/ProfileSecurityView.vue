<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Check, Clipboard, Eye, EyeOff, KeyRound, Loader2, RefreshCw, UserRound } from 'lucide-vue-next';

import { ManagerService } from '../client';
import { clearManagerSession, managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import {
  generateManagerPassword,
  passwordPolicyMessage,
} from '../services/manager-account-security';
import { getApiErrorMessage } from '../utils/api-errors';

const emit = defineEmits<{ passwordChanged: [] }>();

const currentPassword = ref('');
const newPassword = ref('');
const confirmation = ref('');
const error = ref('');
const submitting = ref(false);
const showNewPassword = ref(false);
const generatedPassword = ref('');
const generatedPasswordSaved = ref(false);
const copySucceeded = ref(false);
const copyingPassword = ref(false);
const canChangePassword = computed(() => managerSession.auth.value?.can_change_password === true);
const account = computed(() => managerSession.auth.value);
const storefrontName = computed(() => {
  const selected = managerStorefrontSelection.selectedSlug.value;
  return managerStorefrontSelection.storefronts.value.find(
    storefront => storefront.slug === selected,
  )?.display_name || 'Текущий филиал';
});
const roleLabel = computed(() => ({
  owner: 'Владелец',
  admin: 'Администратор',
  manager: 'Менеджер',
}[String(account.value?.role || '').toLowerCase()] || account.value?.role || 'Не указана'));

const generatePassword = () => {
  const generated = generateManagerPassword();
  newPassword.value = generated;
  confirmation.value = generated;
  generatedPassword.value = generated;
  generatedPasswordSaved.value = false;
  copySucceeded.value = false;
  showNewPassword.value = true;
  error.value = '';
};

const copyPassword = async () => {
  if (!generatedPassword.value || copyingPassword.value) return;
  const passwordSnapshot = newPassword.value;
  copyingPassword.value = true;
  try {
    await window.navigator.clipboard.writeText(passwordSnapshot);
    if (
      newPassword.value !== passwordSnapshot
      || confirmation.value !== passwordSnapshot
    ) {
      copySucceeded.value = false;
      generatedPasswordSaved.value = false;
      error.value = 'Пароль изменился во время копирования. Скопируйте его ещё раз.';
      return;
    }
    generatedPassword.value = passwordSnapshot;
    copySucceeded.value = true;
    generatedPasswordSaved.value = true;
    error.value = '';
  } catch {
    copySucceeded.value = false;
    error.value = 'Не удалось скопировать пароль. Скопируйте его из открытого поля вручную.';
  } finally {
    copyingPassword.value = false;
  }
};

watch([newPassword, confirmation], ([nextPassword, nextConfirmation]) => {
  if (
    generatedPasswordSaved.value
    && (
      nextPassword !== generatedPassword.value
      || nextConfirmation !== generatedPassword.value
    )
  ) {
    generatedPasswordSaved.value = false;
    copySucceeded.value = false;
  }
});

const submit = async () => {
  if (submitting.value || !canChangePassword.value) return;
  error.value = '';

  const policyError = passwordPolicyMessage(newPassword.value);
  if (policyError) {
    error.value = policyError;
    return;
  }
  if (newPassword.value !== confirmation.value) {
    error.value = 'Новый пароль и повтор не совпадают';
    return;
  }
  if (generatedPassword.value && !generatedPasswordSaved.value) {
    error.value = 'Сохраните сгенерированный пароль перед сменой';
    return;
  }

  submitting.value = true;
  try {
    await ManagerService.changeManagerAccountPassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
    });
    currentPassword.value = '';
    newPassword.value = '';
    confirmation.value = '';
    generatedPassword.value = '';
    generatedPasswordSaved.value = false;
    copySucceeded.value = false;
    clearManagerSession();
    emit('passwordChanged');
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError) || 'Не удалось изменить пароль';
  } finally {
    submitting.value = false;
  }
};
</script>

<template>
  <section class="mx-auto max-w-xl px-4 py-8 sm:px-6">
    <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div class="flex items-start gap-3">
        <div class="rounded-lg bg-teal-50 p-2 text-teal-700"><KeyRound class="h-5 w-5" /></div>
        <div>
          <h1 class="text-xl font-semibold text-gray-900">Профиль / Безопасность</h1>
          <p class="mt-1 text-sm text-gray-600">После смены пароля потребуется войти заново.</p>
        </div>
      </div>

      <div class="mt-6 rounded-xl border border-gray-200 bg-gray-50 p-4">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-full bg-teal-100 text-teal-700">
            <UserRound class="h-5 w-5" />
          </div>
          <div class="min-w-0">
            <p class="truncate font-semibold text-gray-900">{{ account?.display_name || account?.username }}</p>
            <p class="truncate text-xs text-gray-500">{{ account?.username }}</p>
          </div>
        </div>
        <dl class="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt class="text-xs text-gray-500">Роль</dt><dd class="mt-0.5 font-medium text-gray-800">{{ roleLabel }}</dd></div>
          <div><dt class="text-xs text-gray-500">Филиал</dt><dd class="mt-0.5 font-medium text-gray-800">{{ storefrontName }}</dd></div>
        </dl>
      </div>

      <div v-if="!canChangePassword" data-testid="password-change-unavailable" class="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Самостоятельная смена пароля недоступна для этой учётной записи.
      </div>

      <form v-else class="mt-6 space-y-4" @submit.prevent="submit">
        <label class="block text-sm font-medium text-gray-700" for="current-password">
          Текущий пароль
          <input id="current-password" v-model="currentPassword" class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2" type="password" autocomplete="current-password" required />
        </label>
        <label class="block text-sm font-medium text-gray-700" for="new-password">
          Новый пароль
          <input id="new-password" v-model="newPassword" class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2" :type="showNewPassword ? 'text' : 'password'" autocomplete="new-password" required />
        </label>
        <label class="block text-sm font-medium text-gray-700" for="password-confirmation">
          Повторите новый пароль
          <input id="password-confirmation" v-model="confirmation" class="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2" :type="showNewPassword ? 'text' : 'password'" autocomplete="new-password" required />
        </label>
        <div class="flex flex-wrap gap-3">
          <button type="button" class="inline-flex items-center gap-2 text-sm font-medium text-teal-700 hover:text-teal-800" @click="generatePassword">
            <RefreshCw class="h-4 w-4" /> Сгенерировать надёжный пароль
          </button>
          <button type="button" class="inline-flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900" @click="showNewPassword = !showNewPassword">
            <EyeOff v-if="showNewPassword" class="h-4 w-4" />
            <Eye v-else class="h-4 w-4" />
            {{ showNewPassword ? 'Скрыть пароль' : 'Показать пароль' }}
          </button>
        </div>
        <div v-if="generatedPassword" class="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
          <p>Сохраните сгенерированный пароль: после смены текущая сессия завершится.</p>
          <button type="button" data-testid="copy-generated-password" class="mt-2 inline-flex items-center gap-2 font-medium text-blue-800 hover:text-blue-950 disabled:cursor-wait disabled:opacity-60" :disabled="copyingPassword" @click="copyPassword">
            <Check v-if="copySucceeded" class="h-4 w-4" />
            <Clipboard v-else class="h-4 w-4" />
            {{ copyingPassword ? 'Копируем...' : copySucceeded ? 'Пароль скопирован' : 'Скопировать пароль' }}
          </button>
          <label class="mt-3 flex items-start gap-2">
            <input v-model="generatedPasswordSaved" data-testid="generated-password-saved" type="checkbox" class="mt-0.5" />
            <span>Я сохранил пароль и смогу войти с ним снова</span>
          </label>
        </div>
        <p v-if="error" role="alert" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <button class="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 font-medium text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60" type="submit" :disabled="submitting">
          <Loader2 v-if="submitting" class="h-4 w-4 animate-spin" />
          {{ submitting ? 'Сохраняем...' : 'Сменить пароль' }}
        </button>
      </form>
    </div>
  </section>
</template>
