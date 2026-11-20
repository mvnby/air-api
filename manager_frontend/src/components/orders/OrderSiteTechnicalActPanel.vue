<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue';
import {
  ManagerDocsService,
  ManagerDocumentSystemService,
  ManagerOrderDiagnosticsService,
  type DocumentLegalEntityItem,
  type ManagedDocumentItem,
  type ManagerOrderDetailResponse,
  type ManagerOrderDocumentItem,
  type OrderInspectionState,
  type OrderSiteEquipmentItem,
  type OrderSiteItem,
  type OrderTechnicalActPrepared,
  type PrepareOrderTechnicalActPayload,
} from '../../client';
import { useNativeDocumentBasis } from '../../features/documents/composables/use-native-document-basis';
import { getApiErrorMessage } from '../../utils/api-errors';
import { equipmentTitle } from '../equipment/registry';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  site: OrderSiteItem;
  equipment: OrderSiteEquipmentItem[];
  inspections: Record<number, OrderInspectionState>;
  loadInspection: (id: number, force?: boolean) => Promise<OrderInspectionState | undefined>;
  disabled: boolean;
  beforeAction: () => Promise<boolean>;
}>();
const emit = defineEmits<{ busy: [busy: boolean]; stale: []; close: [] }>();

const documentType = ref<PrepareOrderTechnicalActPayload['document_type']>('technical_inspection_act');
const issueDate = ref(new Date().toLocaleDateString('sv-SE'));
const legalEntityId = ref<number | null>(null);
const baseDocumentId = ref<number | null>(null);
const baseCustomerContractId = ref<number | null>(null);
const legalEntities = ref<DocumentLegalEntityItem[]>([]);
const documents = ref<ManagedDocumentItem[]>([]);
const orderDocuments = ref<ManagerOrderDocumentItem[]>([]);
const loading = ref(false);
const busy = ref(false);
const loadError = ref('');
const commandError = ref('');
const selectedIds = ref<number[]>([]);
const checking = ref(new Set<number>());
const inspectionErrors = ref<Record<number, string>>({});
const result = ref<OrderTechnicalActPrepared | null>(null);
let active = true;
let intent: { fingerprint: string; request: PrepareOrderTechnicalActPayload } | undefined;
onScopeDispose(() => { active = false; });

const basis = useNativeDocumentBasis({
  order: () => props.order, documents, orderDocuments, documentType, issueDate,
  legalEntityId, legalEntities, baseDocumentId, baseCustomerContractId, requireExplicitSelection: true,
});
const selected = computed(() => props.equipment.filter(item => selectedIds.value.includes(item.equipment_id)));
const scopes = computed(() => selected.value.flatMap(item => {
  const current = props.inspections[item.equipment_id];
  return current?.inspection?.version === current?.current_version && current?.current_version
    ? [{ equipment_id: item.equipment_id, expected_version: current.current_version }]
    : [];
}));
const hasDefect = computed(() => selected.value.some(item => props.inspections[item.equipment_id]?.inspection?.status === 'defect_found'));
const formError = computed(() => {
  if (!selected.value.length || checking.value.size) return '';
  if (selected.value.some(item => inspectionErrors.value[item.equipment_id])) return 'Проверьте, что загружены актуальные версии осмотров.';
  if (scopes.value.length !== selected.value.length) return 'Для каждой выбранной единицы нужно сохранить осмотр.';
  if (documentType.value === 'defect_act' && !hasDefect.value) return 'В выбранных осмотрах должен быть зафиксирован дефект.';
  return '';
});
const canSubmit = computed(() => !props.disabled && !busy.value && !loading.value && !checking.value.size
  && !formError.value && selected.value.length > 0 && selected.value.length <= 100
  && Boolean(legalEntityId.value && issueDate.value && basis.selected.value));

const loadBasis = async () => {
  loading.value = true;
  loadError.value = '';
  try {
    const [issuers, native, legacy] = await Promise.all([
      ManagerDocumentSystemService.listManagerDocumentLegalEntities(),
      ManagerDocumentSystemService.listManagerManagedOrderDocuments(props.order.id),
      ManagerDocsService.getManagerOrderDocuments(props.order.id),
    ]);
    if (!active) return;
    legalEntities.value = issuers.items.filter(item => item.status === 'active');
    documents.value = native.items;
    orderDocuments.value = legacy.items;
  } catch (error) {
    if (active) loadError.value = getApiErrorMessage(error);
  } finally {
    if (active) loading.value = false;
  }
};
const checkInspection = async (id: number, force = false) => {
  if (checking.value.has(id)) return;
  checking.value.add(id);
  delete inspectionErrors.value[id];
  try {
    if (!await props.loadInspection(id, force) && active) {
      inspectionErrors.value[id] = 'Не удалось загрузить осмотр';
    }
  } finally {
    if (active) checking.value.delete(id);
  }
};
const selectEquipment = (id: number, event: Event) => {
  if ((event.target as HTMLInputElement).checked) {
    if (selectedIds.value.length >= 100) return;
    selectedIds.value = [...selectedIds.value, id];
    void checkInspection(id);
  } else {
    selectedIds.value = selectedIds.value.filter(item => item !== id);
  }
};
const prepare = async () => {
  if (!canSubmit.value || !legalEntityId.value) return;
  const payload = {
    expected_site_version: props.site.version,
    document_type: documentType.value,
    inspections: scopes.value,
    legal_entity_id: legalEntityId.value,
    issue_date: issueDate.value,
    base_document_id: baseDocumentId.value,
    base_customer_contract_id: baseCustomerContractId.value,
  };
  const fingerprint = JSON.stringify(payload);
  if (intent?.fingerprint !== fingerprint) {
    intent = { fingerprint, request: { ...payload, idempotency_key: crypto.randomUUID() } };
  }
  const request = intent.request;
  busy.value = true;
  commandError.value = '';
  result.value = null;
  emit('busy', true);
  try {
    if (!await props.beforeAction() || !active) return;
    const response = await ManagerOrderDiagnosticsService.prepareManagerOrderTechnicalAct(props.order.id, props.site.id, request);
    if (!active) return;
    result.value = response.result;
    intent = undefined;
  } catch (error) {
    if (!active) return;
    commandError.value = getApiErrorMessage(error);
    if ((error as { status?: number })?.status === 409) {
      emit('stale');
      // Limit parallel reads when a draft spans many inspected units.
      for (const item of selected.value) {
        if (!active) break;
        await checkInspection(item.equipment_id, true);
      }
    }
  } finally {
    if (active) {
      busy.value = false;
      emit('busy', false);
    }
  }
};

onMounted(loadBasis);
</script>

<template>
  <form class="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700" data-testid="prepare-site-technical-act" @submit.prevent="prepare">
    <fieldset class="space-y-3" :disabled="disabled || busy">
      <legend class="text-sm font-semibold">Подготовка технического акта</legend>
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="field-label">
          Вид документа
          <select v-model="documentType" class="field-input">
            <option value="technical_inspection_act">Акт технического обследования</option>
            <option value="defect_act">Дефектный акт</option>
          </select>
        </label>
        <label class="field-label">Дата акта<input v-model="issueDate" class="field-input" type="date" required /></label>
      </div>

      <fieldset class="space-y-2">
        <legend class="text-xs font-semibold">Оборудование объекта</legend>
        <div v-for="item in equipment" :key="item.equipment_id" class="flex min-w-0 flex-wrap items-center gap-2 text-sm">
          <label class="flex min-w-0 items-start gap-2 break-words">
            <input
              class="mt-0.5"
              :value="item.equipment_id"
              type="checkbox"
              :checked="selectedIds.includes(item.equipment_id)"
              :disabled="selectedIds.length >= 100 && !selectedIds.includes(item.equipment_id)"
              @change="selectEquipment(item.equipment_id, $event)"
            />
            {{ equipmentTitle(item.equipment) }}
          </label>
          <span v-if="checking.has(item.equipment_id)" role="status" class="text-xs text-slate-500">Проверяем осмотр…</span>
          <span v-else-if="inspections[item.equipment_id]?.current_version" class="text-xs text-slate-500">Осмотр v{{ inspections[item.equipment_id]?.current_version }}</span>
          <span v-else-if="selectedIds.includes(item.equipment_id) && !inspectionErrors[item.equipment_id]" class="text-xs text-slate-500">Осмотр не сохранён</span>
          <button v-if="inspectionErrors[item.equipment_id] && selectedIds.includes(item.equipment_id)" class="text-xs text-red-700 underline dark:text-red-300" type="button" @click="checkInspection(item.equipment_id, true)">Повторить загрузку осмотра</button>
        </div>
        <p v-if="formError" class="text-sm text-amber-800 dark:text-amber-300" role="status">{{ formError }}</p>
      </fieldset>

      <p v-if="loading || basis.loading.value" role="status" class="text-xs text-slate-500">Загружаем реквизиты и договоры…</p>
      <p v-if="loadError" role="alert" class="text-sm text-red-700 dark:text-red-300">
        {{ loadError }} <button class="underline" type="button" @click="loadBasis">Повторить</button>
      </p>
      <p v-if="basis.loadError.value" role="alert" class="text-sm text-red-700 dark:text-red-300">
        {{ basis.loadError.value }} <button class="underline" type="button" @click="basis.reload">Повторить</button>
      </p>
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="field-label">
          Наше юридическое лицо
          <select v-model="legalEntityId" class="field-input" :disabled="loading" required>
            <option :value="null">Выберите юридическое лицо</option>
            <option v-for="issuer in legalEntities" :key="issuer.id" :value="issuer.id">{{ issuer.display_name }}</option>
          </select>
        </label>
        <label class="field-label">
          Документ-основание
          <select v-model="basis.value.value" class="field-input" :disabled="!legalEntityId || loading" required>
            <option value="">Выберите договор или оферту</option>
            <option v-for="item in basis.options.value" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
      </div>
      <p v-if="legalEntityId && !loading && !basis.loading.value && !basis.options.value.length" class="text-xs text-slate-500">
        Нет доступного основания. Проверьте договор в разделе «Документы» и юридическое лицо.
      </p>
      <div class="flex flex-wrap justify-end gap-2">
        <button type="button" class="btn-mini-outline" @click="emit('close')">Свернуть</button>
        <button type="submit" class="btn-mini" :disabled="!canSubmit">{{ busy ? 'Готовим…' : 'Подготовить черновик' }}</button>
      </div>
    </fieldset>
    <p v-if="commandError" role="alert" class="break-words text-sm text-red-700 dark:text-red-300">{{ commandError }}</p>
    <p v-if="result" role="status" class="text-sm text-emerald-700 dark:text-emerald-300">
      Черновик создан.
      <a :href="result.manager_url" class="font-semibold underline" target="_blank" rel="noopener">Открыть черновик акта</a>
    </p>
  </form>
</template>
