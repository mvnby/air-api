<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import {
  ManagerMultiSplitService,
  type ManagerMultiSplitPreviewResponse,
  type ManagerOrderDetailResponse,
  type MultiSplitOption,
  type MultiSplitPreviewRequest,
  type MultiSplitRoomInput,
  type OrderProposalResponse,
} from '../../client';
import { useDemoReadOnly } from '../../services/manager-demo';

const props = defineProps<{
  orderId: number;
  proposals: OrderProposalResponse[];
  beforeSave: () => Promise<boolean>;
}>();
const emit = defineEmits<{ updated: [order: ManagerOrderDetailResponse] }>();

const outdoors = ref<MultiSplitOption[]>([]);
const indoors = ref<MultiSplitOption[]>([]);
const outdoorId = ref<number | null>(null);
const rooms = ref<MultiSplitRoomInput[]>([{ name: 'Помещение 1', indoor_product_id: 0 }]);
const preview = ref<ManagerMultiSplitPreviewResponse | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const demoReadOnly = useDemoReadOnly();
let previewRevision = 0;
let previewTimer: ReturnType<typeof setTimeout> | undefined;

const savedConfigurations = computed(() => props.proposals.filter((item) => item.multi_split_configuration && !item.is_archived));
const requestPayload = computed<MultiSplitPreviewRequest | null>(() => {
  if (!outdoorId.value || rooms.value.length === 0 || rooms.value.some((room) => !room.indoor_product_id || !room.name.trim())) return null;
  return { outdoor_product_id: outdoorId.value, rooms: rooms.value.map((room) => ({
    name: room.name.trim(),
    indoor_product_id: room.indoor_product_id,
    area_m2: Number(room.area_m2) > 0 ? Number(room.area_m2) : undefined,
    required_cooling_kw: Number(room.required_cooling_kw) > 0 ? Number(room.required_cooling_kw) : undefined,
    preferred_form: room.preferred_form || undefined,
  })) };
});
const money = (value: number | null | undefined) => value == null ? 'нет данных' : `${new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 2 }).format(value)} BYN`;
const availabilityLabel = (value: string) => ({
  in_stock_now: 'В наличии',
  available_2_3_days: 'Доступен за 2–3 дня',
  check_availability: 'Уточнить наличие',
  out_of_stock: 'Нет в наличии',
}[value] || 'Уточнить наличие');
const errorText = (cause: unknown) => cause instanceof Error ? cause.message : 'Не удалось выполнить запрос. Повторите попытку.';
const sourceLink = (value: string | null | undefined) => {
  try {
    const url = new URL(value || '');
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch { return null; }
};

async function loadKind(kind: 'outdoor_unit' | 'indoor_unit'): Promise<MultiSplitOption[]> {
  const result: MultiSplitOption[] = [];
  let page = 1;
  while (true) {
    const response = await ManagerMultiSplitService.listManagerMultiSplitOptions(kind, page, 100);
    result.push(...response.items);
    if (page >= response.meta.pages) return result;
    page += 1;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    [outdoors.value, indoors.value] = await Promise.all([loadKind('outdoor_unit'), loadKind('indoor_unit')]);
  } catch (cause) {
    error.value = errorText(cause);
  } finally {
    loading.value = false;
  }
});

function addRoom() {
  if (rooms.value.length < 8) rooms.value.push({ name: `Помещение ${rooms.value.length + 1}`, indoor_product_id: 0 });
}

async function refreshPreview() {
  const revision = ++previewRevision;
  preview.value = null;
  error.value = '';
  const payload = requestPayload.value;
  if (!payload) return;
  try {
    const response = await ManagerMultiSplitService.previewManagerMultiSplit(payload);
    if (revision === previewRevision) preview.value = response;
  } catch (cause) {
    if (revision === previewRevision) error.value = errorText(cause);
  }
}

watch([outdoorId, rooms], () => {
  if (previewTimer) clearTimeout(previewTimer);
  preview.value = null;
  previewTimer = setTimeout(() => { void refreshPreview(); }, 250);
}, { deep: true });
onUnmounted(() => { if (previewTimer) clearTimeout(previewTimer); previewRevision += 1; });

async function save() {
  const payload = requestPayload.value;
  if (!payload || !preview.value || preview.value.status === 'incompatible' || saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    if (!await props.beforeSave()) return;
    const updated = await ManagerMultiSplitService.saveManagerMultiSplitProposal(props.orderId, {
      ...payload,
      expected_status: preview.value.status,
      expected_components: preview.value.components,
    });
    emit('updated', updated);
  } catch (cause) {
    error.value = errorText(cause);
    preview.value = null;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="mb-4 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-slate-800" aria-label="Конфигуратор мультисплитов">
    <h4 class="text-base font-semibold">Мультисплит: отдельный вариант предложения</h4>
    <p class="mt-1 text-xs">Выберите наружный блок и блок для каждого помещения. Цена ниже относится только к оборудованию; монтаж рассчитывается отдельно.</p>
    <p v-if="loading" role="status" class="mt-3">Загружаем компоненты…</p>
    <p v-if="error" role="alert" class="mt-3 text-red-700">{{ error }}</p>
    <template v-if="!loading">
      <p v-if="!outdoors.length || !indoors.length" class="mt-3">Для этого каталога нет доступных отдельных блоков.</p>
      <template v-else>
        <label class="mt-3 block font-medium">Наружный блок
          <select v-model.number="outdoorId" class="field-input mt-1 w-full" data-testid="multi-outdoor">
            <option :value="null">Выберите наружный блок</option>
            <option v-for="item in outdoors" :key="item.id" :value="item.id">{{ item.title }} · {{ money(item.price_byn) }}</option>
          </select>
        </label>
        <div class="mt-3 space-y-3">
          <div v-for="(room, index) in rooms" :key="index" class="rounded-lg border border-sky-200 bg-white p-3">
            <div class="flex items-center justify-between gap-2">
              <strong>Помещение {{ index + 1 }}</strong>
              <button v-if="rooms.length > 1" type="button" class="text-red-700" @click="rooms.splice(index, 1)">Удалить</button>
            </div>
            <div class="mt-2 grid gap-2 md:grid-cols-2">
              <label>Название<input v-model="room.name" maxlength="80" class="field-input mt-1 w-full" /></label>
              <label>Площадь, м²<input v-model.number="room.area_m2" type="number" min="1" max="1000" class="field-input mt-1 w-full" /></label>
              <label>Требуемая мощность, кВт<input v-model.number="room.required_cooling_kw" type="number" min="0.1" max="100" step="0.1" class="field-input mt-1 w-full" /></label>
              <label>Форма блока
                <select v-model="room.preferred_form" class="field-input mt-1 w-full">
                  <option :value="undefined">Любая</option><option value="wall">Настенный</option><option value="cassette">Кассетный</option><option value="duct">Канальный</option><option value="floor_ceiling">Напольно-потолочный</option><option value="console">Консольный</option><option value="column">Колонный</option>
                </select>
              </label>
              <label class="md:col-span-2">Внутренний блок
                <select v-model.number="room.indoor_product_id" class="field-input mt-1 w-full">
                  <option :value="0">Выберите внутренний блок</option>
                  <option v-for="item in indoors" :key="item.id" :value="item.id">{{ item.title }} · {{ money(item.price_byn) }} · {{ availabilityLabel(item.availability) }}</option>
                </select>
              </label>
            </div>
          </div>
        </div>
        <button v-if="rooms.length < 8" type="button" class="btn-mini-outline mt-3" @click="addRoom">Добавить помещение</button>
        <button v-if="requestPayload" type="button" class="btn-mini-outline mt-3 ml-2" @click="refreshPreview">Пересчитать состав и цены</button>
        <div v-if="preview" class="mt-4 rounded-lg bg-white p-3" data-testid="multi-preview">
          <p class="font-semibold">{{ preview.status === 'confirmed' ? 'Совместимость подтверждена' : preview.status === 'incompatible' ? 'Состав несовместим' : 'Требуется проверка специалистом' }}</p>
          <p class="mt-1">{{ preview.explanation }}</p>
          <ul class="mt-2 list-inside list-disc">
            <li v-for="item in preview.components" :key="item.product_id">{{ item.title }} × {{ item.quantity }} — {{ money(item.total_price_byn) }} · {{ availabilityLabel(item.availability) }}</li>
          </ul>
          <p class="mt-2 font-semibold">Оборудование: {{ money(preview.equipment_total_byn) }}</p>
          <p>Закупка: {{ money(preview.purchase_cost_total_byn) }} · Маржа: {{ money(preview.margin_byn) }}</p>
          <p v-if="!preview.composition_complete" class="mt-1 text-amber-800">Состав может требовать обязательных компонентов после проверки.</p>
          <button type="button" class="btn-mini-outline mt-3" :disabled="saving || demoReadOnly || preview.status === 'incompatible'" @click="save">{{ saving ? 'Сохраняем…' : 'Сохранить отдельным вариантом' }}</button>
        </div>
      </template>
    </template>
    <div v-if="savedConfigurations.length" class="mt-4 border-t border-sky-200 pt-3">
      <strong>Сохранённые конфигурации</strong>
      <div v-for="item in savedConfigurations" :key="item.id" class="mt-2 rounded-lg bg-white p-2">
        <p>{{ item.name }} · {{ item.multi_split_configuration?.rooms?.length ?? 0 }} пом. · {{ item.multi_split_configuration?.verification_status === 'confirmed' ? 'подтверждена' : 'требуется проверка' }} · сохранено {{ money(item.total_amount) }}</p>
        <p class="text-xs text-slate-600">{{ item.multi_split_configuration?.component_snapshot?.map((part) => `${part.title} × ${part.quantity}`).join('; ') }}</p>
        <a v-if="sourceLink(item.multi_split_configuration?.source_url)" :href="sourceLink(item.multi_split_configuration?.source_url) || undefined" target="_blank" rel="noopener noreferrer" class="text-xs text-sky-700">Источник совместимости · {{ item.multi_split_configuration?.source_version }}</a>
      </div>
    </div>
  </section>
</template>
