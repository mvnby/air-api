<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ExternalLink, Route } from 'lucide-vue-next';
import { ApiError, ManagerOrdersService } from '../../client';
import type { CancelablePromise, ManagerOrderTravelRouteResponse } from '../../client';
import { buildVitebskRoundTripUrl, normalizeAddressQuery } from '../../utils/address';

const props = defineProps<{ orderId: number; address: string }>();
const address = computed(() => normalizeAddressQuery(props.address));
const mapUrl = computed(() => buildVitebskRoundTripUrl(address.value));
const result = ref<ManagerOrderTravelRouteResponse | null>(null);
const loading = ref(false);
const error = ref('');
let pending: CancelablePromise<ManagerOrderTravelRouteResponse> | null = null;

const messages: Record<string, string> = {
  order_route_not_configured: 'Расчёт маршрута в Manager пока не подключён.',
  order_route_address_not_found: 'Уточните населённый пункт, улицу или номер дома.',
  order_route_not_found: 'Провайдер не нашёл автомобильный маршрут.',
  order_route_rate_limit: 'Подождите немного и повторите расчёт.',
  order_route_provider_limit: 'Сервис маршрутов достиг лимита запросов.',
};

const reset = () => {
  pending?.cancel();
  pending = null;
  loading.value = false;
  result.value = null;
  error.value = '';
};
watch([() => props.orderId, address], reset, { flush: 'sync' });
onBeforeUnmount(reset);

async function calculate() {
  if (!mapUrl.value || loading.value) return;
  loading.value = true;
  error.value = '';
  const request = ManagerOrdersService.calculateManagerOrderTravelRoute(
    props.orderId, { address: address.value },
  );
  pending = request;
  try {
    const route = await request;
    if (pending === request) result.value = route;
  } catch (cause) {
    if (pending !== request) return;
    result.value = null;
    const code = cause instanceof ApiError ? cause.body?.detail?.code : undefined;
    error.value = messages[code] ?? 'Маршрут сейчас недоступен. Его можно открыть на карте.';
  } finally {
    if (pending === request) {
      loading.value = false;
      pending = null;
    }
  }
}

const distance = new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 1 });
const formatDuration = (seconds: number) => {
  const minutes = Math.ceil(seconds / 60);
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} ч ${minutes % 60} мин` : `${minutes} мин`;
};
const legs = computed(() => result.value ? [
  { label: 'Туда', ...result.value.outbound },
  { label: 'Обратно', ...result.value.inbound },
  { label: 'Всего в дороге', ...result.value.total },
] : []);
</script>

<template>
  <section v-if="mapUrl" aria-label="Маршрут из Витебска" class="space-y-2 border-y border-slate-200 py-2 dark:border-slate-700">
    <div class="flex flex-wrap items-center gap-2">
      <button type="button" class="btn-mini-outline gap-1 text-xs" :disabled="loading"
        data-testid="calculate-order-travel-route" @click="calculate">
        <Route :size="15" aria-hidden="true" /> {{ loading ? 'Считаем маршрут…' : 'Рассчитать маршрут из Витебска' }}
      </button>
      <a :href="mapUrl" target="_blank" rel="noopener noreferrer" class="btn-mini-outline gap-1 text-xs">
        <ExternalLink :size="14" aria-hidden="true" /> Открыть в Google Maps
      </a>
    </div>
    <div aria-live="polite" :aria-busy="loading">
      <p v-if="error" class="text-xs text-slate-600 dark:text-slate-300">{{ error }}</p>
      <div v-else-if="result" class="space-y-1 text-xs">
        <p class="text-slate-600 dark:text-slate-300">{{ result.origin }} → {{ result.destination }}</p>
        <dl class="flex flex-wrap gap-x-5 gap-y-2">
          <div v-for="leg in legs" :key="leg.label">
            <dt class="text-slate-500 dark:text-slate-400">{{ leg.label }}</dt>
            <dd class="font-semibold text-slate-900 dark:text-slate-100">
              {{ distance.format(leg.distance_m / 1000) }} км · {{ formatDuration(leg.duration_s) }}
            </dd>
          </div>
        </dl>
        <p v-if="result.approximate_destination" class="text-amber-800 dark:text-amber-300">
          Точка определена приблизительно. Сверьте её на карте.
        </p>
        <p class="text-slate-500 dark:text-slate-400">Оценка Яндекс Карт без времени работ на объекте.</p>
      </div>
    </div>
  </section>
</template>
