<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { ManagerTenderModuleService, type CancelablePromise, type TenderMarketEvidenceResult } from '../../client';
import TenderEvidenceReport from '../../components/leads/TenderEvidenceReport.vue';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ publicationId: number }>();
const snapshot = ref<TenderMarketEvidenceResult | null>(null);
const error = ref('');
const busy = ref(false);
const active = computed(() => snapshot.value?.status === 'queued' || snapshot.value?.status === 'reading');
const sourceLink = computed(() => {
  const value = snapshot.value?.documents_source_url;
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : undefined;
  } catch {
    return undefined;
  }
});
const checkedTime = computed(() => snapshot.value?.checked_at
  ? new Intl.DateTimeFormat('ru-BY', { timeZone: 'Europe/Minsk', dateStyle: 'short', timeStyle: 'short' })
      .format(new Date(snapshot.value.checked_at))
  : null);
let timer: ReturnType<typeof setTimeout> | undefined;
let pending: CancelablePromise<TenderMarketEvidenceResult> | undefined;
let closed = false;

async function receive(request: CancelablePromise<TenderMarketEvidenceResult>, until: number) {
  pending = request;
  try {
    const result = await request;
    if (closed || pending !== request) return;
    snapshot.value = result;
    error.value = result.error || '';
    if (active.value && Date.now() < until) {
      timer = setTimeout(() => void receive(
        ManagerTenderModuleService.getManagerTenderMarketEvidence(props.publicationId), until,
      ), 3_000);
      return;
    }
    busy.value = false;
  } catch (reason) {
    if (!closed && pending === request) {
      error.value = getApiErrorMessage(reason);
      busy.value = false;
    }
  } finally {
    if (pending === request) pending = undefined;
  }
}

function open(check: boolean) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  const request = check
    ? ManagerTenderModuleService.requestManagerTenderMarketEvidence(props.publicationId)
    : ManagerTenderModuleService.getManagerTenderMarketEvidence(props.publicationId);
  void receive(request, Date.now() + 175_000);
}

onMounted(() => open(false));
onBeforeUnmount(() => {
  closed = true;
  clearTimeout(timer);
  pending?.cancel();
});
</script>

<template>
  <section class="mt-3 border-t border-slate-200 pt-3 text-sm dark:border-slate-700" aria-label="Проверка ТЗ">
    <button type="button" class="btn-mini-outline" :disabled="busy" @click="open(!active)">
      {{ active ? 'Обновить состояние' : snapshot?.report ? 'Сверить оригиналы' : 'Проверить ТЗ' }}
    </button>
    <p v-if="active || busy" role="status" class="mt-2 text-xs text-slate-500">
      {{ snapshot?.status === 'queued' ? 'Оригиналы в очереди на проверку.' :
        snapshot?.status === 'reading' ? 'Читаем оригиналы и сверяем требования.' : 'Загружаем состояние проверки.' }}
    </p>
    <p v-if="error" role="alert" class="mt-2 text-xs text-red-700">{{ error }}</p>
    <template v-if="snapshot?.report">
      <div class="mt-2 flex flex-wrap items-baseline gap-3 text-xs">
        <a v-if="sourceLink" :href="sourceLink" target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-700 underline">
          Оригиналы на площадке
        </a>
        <span v-if="checkedTime" class="text-slate-500">Проверено {{ checkedTime }}</span>
      </div>
      <TenderEvidenceReport :report="snapshot.report" />
    </template>
  </section>
</template>
