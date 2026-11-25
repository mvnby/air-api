<script setup lang="ts">
import { ref } from 'vue';
import type { TenderModuleAccess } from '../../client';
import { tenderModuleApi } from '../../services/tender-module';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ tenantId: number; canGrant: boolean }>();
const access = ref<TenderModuleAccess | null>(null);
const pending = ref(false);
const error = ref('');

async function load() {
  if (pending.value) return;
  pending.value = true;
  error.value = '';
  try { access.value = await tenderModuleApi.getCompanyAccess(props.tenantId); }
  catch (reason) { error.value = getApiErrorMessage(reason); }
  finally { pending.value = false; }
}

function open(event: Event) {
  if ((event.currentTarget as HTMLDetailsElement).open && !access.value) void load();
}

async function toggle(event: Event) {
  if (!access.value || pending.value) return;
  const input = event.target as HTMLInputElement;
  const entitled = input.checked;
  const version = access.value.version;
  input.checked = access.value.entitled;
  pending.value = true;
  error.value = '';
  try { access.value = await tenderModuleApi.updateCompanyAccess(props.tenantId, { entitled, version }); }
  catch (reason) { error.value = getApiErrorMessage(reason); }
  finally { pending.value = false; }
}
</script>

<template>
  <details class="rounded-lg border p-3 text-sm" @toggle="open">
    <summary class="cursor-pointer font-semibold">Тендерный модуль</summary>
    <div class="mt-2 space-y-2">
      <p v-if="pending" role="status" class="text-slate-500">Обновляем доступ…</p>
      <p v-if="error" role="alert" class="text-red-700">{{ error }}</p>
      <button v-if="error" type="button" class="btn-mini-outline" :disabled="pending" @click="load">Обновить</button>
      <label v-if="access" class="flex items-center gap-2">
        <input type="checkbox" role="switch" aria-label="Разрешить подключение тендеров" :checked="access.entitled" :disabled="pending || (!canGrant && !access.entitled)" @change="toggle" />
        {{ access.entitled ? 'Подключение разрешено' : 'Подключение закрыто' }}
      </label>
      <p v-if="access?.entitled" class="text-slate-500">{{ access.enabled ? 'Компания подключила модуль.' : 'Компания ещё не подключила модуль.' }}</p>
    </div>
  </details>
</template>
