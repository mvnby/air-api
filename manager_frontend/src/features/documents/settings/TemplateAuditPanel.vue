<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ManagerDocumentSystemService } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { downloadTemplateVersion } from '../integrations/template-download';
import {
  templateAuditApi, type AuditContext, type AuditDecisionStatus, type AuditFinding,
  type TemplateAuditReport,
} from '../integrations/template-audit-api';

const props = defineProps<{ legalEntityId: number | null }>();
const emit = defineEmits<{ toast: [payload: { message: string; type: 'success' | 'error' }]; activated: [] }>();
const reports = ref<TemplateAuditReport[]>([]);
const report = ref<TemplateAuditReport | null>(null);
const selectedId = ref<number | null>(null);
const page = ref(1);
const total = ref(0);
const loading = ref(false);
const busy = ref(false);
const errorMessage = ref('');
const decisions = ref<Record<string, { status: AuditDecisionStatus; reason: string }>>({});
const selectedProposalId = ref<number | null>(null);
const context = ref<AuditContext | null>(null);
const exampleValues = ref<Record<string, string>>({});
const exampleRows = ref<AuditContext['table_rows']>({});
const customerType = ref('individual');
const vat = ref(false);
const partyNames: Record<string, string> = { individual: 'Физлицо', organization: 'Организация', individual_entrepreneur: 'ИП' };
const previewScenarioLabel = computed(() => `${partyNames[customerType.value] || 'Клиент'}, ${vat.value ? 'с НДС' : 'без НДС'} — вымышленные данные`);
const pdfUrl = ref('');
const previewedProposal = ref<number | null>(null);
let generation = 0;
let contextGeneration = 0;
let requestedId = Number(new URLSearchParams(window.location.search).get('auditReportId')) || null;
const proposal = computed(() => report.value?.proposals.find((item) => item.id === selectedProposalId.value) || null);
const locked = computed(() => !report.value || report.value.stale || report.value.coverage.complete !== true);
const proposalLocked = computed(() => locked.value || proposal.value?.stale === true);
const canActivate = computed(() => !proposalLocked.value && proposal.value?.status === 'draft' && previewedProposal.value === selectedProposalId.value && !busy.value);
const decisionOptions: Array<{ value: AuditDecisionStatus; label: string }> = [
  { value: 'proposal', label: 'Предложение' }, { value: 'needs_legal_review', label: 'Нужен юрист' },
  { value: 'accepted', label: 'Принято' }, { value: 'rejected', label: 'Отклонено' }, { value: 'fixed', label: 'Исправлено' },
];
const labels: Record<string, string> = {
  tax_and_price: 'Налоги и цена', subject_and_roles: 'Предмет и роли сторон', payment: 'Оплата', acceptance: 'Приёмка', warranty: 'Гарантия', liability: 'Ответственность', scope_changes: 'Изменение объёма работ', contract_act_annexes: 'Договор, акт и приложения',
  legal_applicability: 'Применимость закона', contradiction: 'Противоречие', tax: 'Налоги', variables: 'Переменные', editorial: 'Редактура',
  low: 'Низкая', medium: 'Средняя', high: 'Высокая', critical: 'Критическая',
  proposal: 'Предложение', needs_legal_review: 'Нужен юрист', accepted: 'Принято', rejected: 'Отклонено', fixed: 'Исправлено',
  source_changed: 'Изменился исходный DOCX', context_changed: 'Изменились реквизиты или условия',
  issuer_template_or_customer_context_changed: 'Изменились реквизиты, условия шаблона или клиента',
  source_version_changed_or_unavailable: 'Исходная версия изменилась или недоступна',
  legal_source_evidence_changed: 'Изменились сохранённые источники права',
  legal_sources_changed: 'Изменились источники права', active_version_changed: 'Сменилась активная версия',
  draft: 'Черновик', active: 'Активна', archived: 'Архив', unavailable: 'Недоступна', checked: 'Проверено', unverified: 'Не проверено', not_applicable: 'Не применяется',
  individual: 'физлицо', organization: 'организация', individual_entrepreneur: 'ИП',
};
const label = (value: string) => labels[value] || value;
const technicalText = (value: unknown) => JSON.stringify(value, null, 2);
const date = (value: string) => new Date(value).toLocaleString('ru-RU');
const reportLabel = (value: TemplateAuditReport) => `${value.template_name || 'Шаблон'} · версия ${value.version_number || 'без номера'} · проверка ${date(value.checked_at)}`;
const coverageReasons: Record<string, string> = {
  field_instruction: 'Есть поля Word, например номера страниц PAGE и NUMPAGES. Адресная правка отключена; откройте исходный DOCX для проверки и редактирования.',
  source_unavailable_or_invalid: 'Исходный DOCX недоступен или повреждён. Проверьте исходник в библиотеке шаблонов вручную.',
  source_unavailable: 'Исходный DOCX недоступен. Откройте исходник в библиотеке шаблонов и проверьте его вручную.',
  unsupported_renderer: 'Этот шаблон использует другой способ подготовки документа. Откройте исходник для ручной проверки.',
  no_active_version: 'У шаблона нет активной версии. Выберите исходный DOCX для проверки.',
  source_integrity_failed: 'Целостность исходного DOCX не подтверждена. Повторно проверьте исходник в библиотеке.',
  drawing: 'В шаблоне есть рисунок с содержимым, которое не удалось полностью проверить. Откройте исходный DOCX.',
  textbox: 'В шаблоне есть текстовый блок особого формата. Для его проверки откройте исходный DOCX.',
  field: 'Есть поля Word. Адресная правка отключена; откройте исходный DOCX.',
  tracked_changes: 'В документе есть исправления в режиме рецензирования. Проверьте и примите их в исходном DOCX.',
  embedded_part: 'В документе есть вложенные объекты. Для полной проверки откройте исходный DOCX.',
  embedded_object: 'В документе есть вложенные объекты. Для полной проверки откройте исходный DOCX.',
  subdocument: 'В документе есть вложенный документ. Проверьте его отдельно в исходном DOCX.',
  bound_content_control: 'Часть текста связана с внешними данными. Проверьте её вручную в исходном DOCX.',
  alt_chunk: 'Часть текста вставлена из другого документа. Откройте исходный DOCX для полной проверки.',
  alternate_content: 'Есть альтернативные варианты содержимого Word. Откройте исходный DOCX для полной проверки.',
  unparsed_story: 'Не удалось прочитать всю часть документа. Откройте исходный DOCX для полной проверки.',
  unparsed_text: 'Не удалось прочитать весь текст документа. Откройте исходный DOCX для полной проверки.',
  unparsed_part: 'Есть часть документа, которую не удалось прочитать. Откройте исходный DOCX для полной проверки.',
  missing_relationship_target: 'В документе отсутствует связанный файл. Проверьте исходный DOCX.',
  invalid_relationship_target: 'В документе есть некорректная ссылка на связанный файл. Проверьте исходный DOCX.',
  symbol: 'Есть символы Word, которые требуют ручной проверки в исходном DOCX.',
  positioned_tab: 'Есть специальное позиционирование текста Word. Проверьте исходный DOCX.',
};
const coverageMessages = computed(() => [...new Set((report.value?.coverage.reasons || []).map((reason) => {
  const code = typeof reason === 'string' ? reason : reason && typeof reason === 'object' ? String((reason as Record<string, unknown>).code || '') : '';
  return coverageReasons[code] || 'Есть элементы, которые не удалось полностью проверить. Адресная правка отключена; откройте исходный DOCX.';
}))]);
const paragraphNumber = (location: unknown) => typeof location === 'string' ? [...location.matchAll(/p\[(\d+)\]/g)].pop()?.[1] : undefined;
const locationLabel = (part?: string, location?: unknown) => {
  const section = part?.includes('header') ? 'Верхний колонтитул' : part?.includes('footer') ? 'Нижний колонтитул'
    : part?.includes('footnotes') ? 'Сноски' : part?.includes('endnotes') ? 'Концевые сноски'
      : part?.includes('comments') ? 'Комментарии' : part?.includes('document') ? 'Основной текст' : 'Фрагмент шаблона';
  const paragraph = paragraphNumber(location);
  return `${section}${paragraph ? ` · абзац ${paragraph}` : ''}`;
};
const findingLocation = (finding: AuditFinding) => {
  const occurrence = finding.occurrences?.find((item) => item.block_id === finding.block_id);
  if (!finding.location_label) return locationLabel(occurrence?.part, occurrence?.location);
  const paragraph = paragraphNumber(occurrence?.location);
  return `${finding.location_label}${paragraph ? ` · абзац ${paragraph}` : ''}`;
};
const fieldLabel = (name: string, index: number) => context.value?.field_labels?.[name] || `Поле ${index + 1}`;
const conditionLabel = (name: string, index: number) => context.value?.condition_labels?.[name] || `Дополнительное условие ${index + 1}`;
const tableLabel = (name: string, index: number) => context.value?.table_labels?.[name] || `Таблица ${index + 1}`;
const rowFieldLabel = (name: string, index: number) => context.value?.row_field_labels?.[name] || `Поле строки ${index + 1}`;
const additionalConditions = computed(() => Object.keys(context.value?.conditions || {}).filter((name) => ![
  'customer.is_individual', 'customer.is_organization', 'customer.is_individual_entrepreneur',
  'seller.is_vat_payer', 'seller.is_not_vat_payer',
].includes(name)));
const sourceUrl = (value: string) => {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
};
const clearPreview = () => {
  if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value);
  pdfUrl.value = '';
  previewedProposal.value = null;
};
const resetContext = () => { ++contextGeneration; context.value = null; clearPreview(); };
const notify = (message: string) => emit('toast', { message, type: 'success' });
const setReport = (value: TemplateAuditReport) => {
  if (value.legal_entity_id !== props.legalEntityId) throw new Error('Этот отчёт относится к другой организации. Откройте его по полной ссылке.');
  report.value = value;
  selectedId.value = value.id;
  decisions.value = Object.fromEntries(value.findings.map((item) => [item.id, { status: item.status, reason: '' }]));
  const previous = selectedProposalId.value;
  selectedProposalId.value = value.proposals.some((item) => item.id === previous) ? previous : value.proposals[0]?.id || null;
  resetContext();
};
const openReport = async (id: number) => {
  const current = ++generation;
  loading.value = true;
  errorMessage.value = '';
  report.value = null;
  resetContext();
  try {
    const result = await templateAuditApi.get(id);
    if (current === generation) setReport(result);
  } catch (error) {
    if (current === generation) errorMessage.value = getApiErrorMessage(error);
  } finally { if (current === generation) loading.value = false; }
};
const loadReports = async (requested?: number | null) => {
  const issuer = props.legalEntityId;
  const current = ++generation;
  report.value = null;
  reports.value = [];
  resetContext();
  errorMessage.value = '';
  if (!issuer) return;
  loading.value = true;
  try {
    const result = await templateAuditApi.list(issuer, page.value);
    if (current !== generation) return;
    reports.value = result.items;
    total.value = result.total;
    const id = requested || result.items[0]?.id;
    selectedId.value = id || null;
    if (id) await openReport(id);
  } catch (error) { if (current === generation) errorMessage.value = getApiErrorMessage(error); }
  finally { if (current === generation) loading.value = false; }
};
watch(() => props.legalEntityId, (issuer) => {
  page.value = 1;
  busy.value = false;
  const requested = requestedId;
  if (issuer) requestedId = null;
  void loadReports(requested);
}, { immediate: true });
watch(selectedProposalId, resetContext);
watch([customerType, vat], clearPreview);
watch(() => [context.value?.values, context.value?.conditions, context.value?.table_rows], clearPreview, { deep: true });
onBeforeUnmount(() => { ++generation; ++contextGeneration; clearPreview(); });

const decide = async (finding: AuditFinding) => {
  const currentReport = report.value;
  const decision = decisions.value[finding.id];
  if (!currentReport || !decision?.reason.trim() || locked.value || busy.value) return;
  const current = generation;
  busy.value = true;
  errorMessage.value = '';
  try {
    const updated = await templateAuditApi.decide(currentReport.id, finding.id, {
      expected_revision: currentReport.revision, source_hash: currentReport.source_hash,
      context_hash: currentReport.context_hash, legal_sources_hash: currentReport.legal_sources_hash,
      status: decision.status, reason: decision.reason.trim(),
    });
    if (current !== generation) return;
    setReport(updated);
    notify('Решение сохранено');
  } catch (error) { if (current === generation) errorMessage.value = `${getApiErrorMessage(error)} Обновите отчёт перед повторной попыткой.`; }
  finally { if (current === generation) busy.value = false; }
};
const loadOccurrences = async (finding: AuditFinding, pageNumber = finding.occurrences_next_page) => {
  const currentReport = report.value;
  if (!currentReport || !pageNumber || busy.value) return;
  const current = generation;
  busy.value = true;
  errorMessage.value = '';
  try {
    const updated = await templateAuditApi.get(currentReport.id, { findingId: finding.id, page: pageNumber });
    if (current !== generation) return;
    if (updated.revision !== currentReport.revision) {
      setReport(updated);
      throw new Error('Отчёт изменился. Проверьте обновлённые замечания перед сохранением решения.');
    }
    const match = updated.findings.find((item) => item.id === finding.id);
    if (match && report.value) {
      Object.assign(finding, {
        occurrences: match.occurrences, occurrences_total: match.occurrences_total,
        occurrences_page: match.occurrences_page, occurrences_next_page: match.occurrences_next_page,
      });
      report.value.stale = updated.stale;
      report.value.stale_reasons = updated.stale_reasons;
    }
  } catch (error) { if (current === generation) errorMessage.value = getApiErrorMessage(error); }
  finally { if (current === generation) busy.value = false; }
};
const downloadSource = async (versionId: number) => {
  const currentReport = report.value;
  if (!currentReport || busy.value) return;
  const current = generation;
  busy.value = true;
  try {
    const versions = await ManagerDocumentSystemService.listManagerNativeTemplateVersions(currentReport.template_id, currentReport.legal_entity_id);
    const version = versions.items.find((item) => item.id === versionId);
    if (current !== generation) return;
    if (!version) throw new Error('Версия шаблона недоступна');
    await downloadTemplateVersion(currentReport.legal_entity_id, version);
  } catch (error) { if (current === generation) errorMessage.value = getApiErrorMessage(error); }
  finally { if (current === generation) busy.value = false; }
};
const loadContext = async () => {
  const currentReport = report.value;
  const currentProposal = proposal.value;
  if (!currentReport || !currentProposal || proposalLocked.value || busy.value) return;
  const current = generation;
  const currentContext = ++contextGeneration;
  busy.value = true;
  errorMessage.value = '';
  try {
    const result = await templateAuditApi.context(currentReport.id, currentProposal.id);
    if (current !== generation || currentContext !== contextGeneration) return;
    context.value = result;
    exampleValues.value = { ...result.values };
    exampleRows.value = structuredClone(result.table_rows);
    customerType.value = result.conditions['customer.is_organization'] ? 'organization'
      : result.conditions['customer.is_individual_entrepreneur'] ? 'individual_entrepreneur' : 'individual';
    vat.value = Boolean(result.conditions['seller.is_vat_payer']);
  } catch (error) { if (current === generation) errorMessage.value = getApiErrorMessage(error); }
  finally { if (current === generation) busy.value = false; }
};
const applyScenario = () => {
  if (!context.value) return;
  const conditions = context.value.conditions;
  const organization = customerType.value === 'organization';
  const entrepreneur = customerType.value === 'individual_entrepreneur';
  const individual = customerType.value === 'individual';
  const scenario: Record<string, boolean> = {
    'customer.is_organization': organization, 'customer.is_individual_entrepreneur': entrepreneur, 'customer.is_individual': individual,
    'customer.signs_self': !organization, 'customer.signs_as_statutory_body': organization, 'customer.signs_by_power_of_attorney': false,
    'customer.organization_statutory_body': organization, 'customer.organization_power_of_attorney': false,
    'customer.individual_entrepreneur_self': entrepreneur, 'customer.individual_entrepreneur_power_of_attorney': false,
    'customer.individual_self': individual, 'customer.individual_power_of_attorney': false,
    'seller.is_vat_payer': vat.value, 'seller.is_not_vat_payer': !vat.value,
  };
  for (const key of Object.keys(conditions)) {
    if (key in scenario) conditions[key] = scenario[key]!;
  }
  const scenarioValues: Record<string, string> = {
    'customer.entity_type': customerType.value,
    'customer.entity_type_label': label(customerType.value),
    'seller.is_vat_payer': vat.value ? 'Да' : 'Нет',
    'totals.vat_label': vat.value ? 'ТЕСТ: с НДС' : 'ТЕСТ: без НДС',
  };
  for (const key of Object.keys(context.value.values)) {
    if (key in scenarioValues) context.value.values[key] = scenarioValues[key]!;
  }
};
const toggleEmpty = (name: string) => {
  if (!context.value) return;
  context.value.values[name] = context.value.values[name] ? '' : exampleValues.value[name] || '';
};
const addRow = (name: string) => {
  if (!context.value) return;
  const fields = exampleRows.value[name]?.[0] || context.value.table_rows[name]?.[0] || {};
  context.value.table_rows[name]?.push(Object.fromEntries(Object.entries(fields).map(([key, value]) => [key, value])));
};
const renderPreview = async (format: 'pdf' | 'docx') => {
  const currentReport = report.value;
  const currentProposal = proposal.value;
  if (!currentReport || !currentProposal || !context.value || proposalLocked.value || busy.value) return;
  const current = generation;
  const currentContext = contextGeneration;
  busy.value = true;
  errorMessage.value = '';
  try {
    const blob = await templateAuditApi.preview(currentReport.id, currentProposal.id, {
      ...context.value, synthetic: true, label: previewScenarioLabel.value,
      format,
    });
    if (current !== generation || currentContext !== contextGeneration) return;
    const url = URL.createObjectURL(blob);
    if (format === 'pdf') {
      clearPreview();
      pdfUrl.value = url;
      previewedProposal.value = currentProposal.id;
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = `Учебный пример — ${currentReport.template_name.replace(/[\\/:*?"<>|]/g, '-')}.docx`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    }
  } catch (error) { if (current === generation) errorMessage.value = getApiErrorMessage(error); }
  finally { if (current === generation) busy.value = false; }
};
const activate = async () => {
  const currentReport = report.value;
  const currentProposal = proposal.value;
  if (!currentReport || !currentProposal || !canActivate.value) return;
  const current = generation;
  busy.value = true;
  errorMessage.value = '';
  try {
    const fresh = await templateAuditApi.get(currentReport.id);
    if (current !== generation) return;
    const freshProposal = fresh.proposals.find((item) => item.id === currentProposal.id);
    if (fresh.stale || fresh.coverage.complete !== true || !freshProposal || freshProposal.stale || freshProposal.status !== 'draft'
      || freshProposal.source_hash !== currentProposal.source_hash || freshProposal.version_id !== currentProposal.version_id
      || fresh.revision !== currentReport.revision || fresh.source_hash !== currentReport.source_hash
      || fresh.context_hash !== currentReport.context_hash || fresh.legal_sources_hash !== currentReport.legal_sources_hash) {
      setReport(fresh);
      throw new Error('Отчёт изменился. Проверьте обновлённый отчёт и предпросмотр.');
    }
    const versions = await ManagerDocumentSystemService.listManagerNativeTemplateVersions(currentReport.template_id, currentReport.legal_entity_id);
    if (current !== generation) return;
    const active = versions.items.find((item) => item.status === 'active');
    const candidate = versions.items.find((item) => item.id === currentProposal.version_id);
    if (!candidate || candidate.status !== 'draft' || candidate.checksum_sha256 !== currentProposal.source_hash) {
      throw new Error('Версии шаблона изменились. Обновите отчёт и выполните новую проверку.');
    }
    await ManagerDocumentSystemService.activateManagerNativeTemplateVersion(
      currentReport.template_id, currentProposal.version_id, currentReport.legal_entity_id, active?.id ?? null,
    );
    if (current !== generation) return;
    emit('activated');
    notify('Новая версия активирована для будущих документов');
    const updated = await templateAuditApi.get(currentReport.id);
    if (current === generation) setReport(updated);
  } catch (error) { if (current === generation) errorMessage.value = getApiErrorMessage(error); }
  finally { if (current === generation) busy.value = false; }
};
</script>

<template>
  <section v-if="legalEntityId" class="settings-card mt-6 space-y-5" aria-labelledby="template-audit-title" data-testid="template-audit-panel">
    <header>
      <h2 id="template-audit-title" class="settings-title">Проверка шаблонов</h2>
      <p class="settings-help">Сохранённые отчёты, замечания и предлагаемые версии DOCX. Решения и предпросмотр не меняют документы клиентов.</p>
    </header>
    <div class="flex flex-wrap items-end gap-3">
      <label class="settings-field min-w-0 flex-1"><span>Сохранённый отчёт</span>
        <select v-model="selectedId" class="settings-input" data-testid="audit-report-select" :disabled="loading || busy || !reports.length" @change="selectedId && openReport(selectedId)">
          <option v-if="report && !reports.some(item => item.id === report?.id)" :value="report.id">{{ reportLabel(report) }}</option>
          <option v-for="item in reports" :key="item.id" :value="item.id">{{ reportLabel(item) }}</option>
        </select>
      </label>
      <button type="button" class="settings-button-secondary" :disabled="loading || busy" @click="report ? openReport(report.id) : loadReports()">Обновить</button>
    </div>
    <div v-if="total > 25" class="flex items-center gap-3 text-sm">
      <button type="button" class="settings-button-secondary" :disabled="page <= 1 || loading || busy" @click="page--; loadReports()">Назад</button>
      <span>Страница {{ page }} · всего {{ total }}</span>
      <button type="button" class="settings-button-secondary" :disabled="page * 25 >= total || loading || busy" @click="page++; loadReports()">Далее</button>
    </div>
    <p v-if="errorMessage" class="rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200" role="alert">{{ errorMessage }}</p>
    <p v-if="loading" class="text-sm text-slate-500" role="status">Загружаем отчёт…</p>
    <p v-else-if="!report && !errorMessage" class="text-sm text-slate-500">Для этой организации ещё нет сохранённых отчётов.</p>
    <div v-if="report" class="space-y-5">
      <div class="rounded-xl bg-slate-50 p-4 text-sm leading-6 dark:bg-slate-800">
        <p class="font-semibold">{{ report.template_name }} · версия {{ report.version_number }}</p>
        <p>Проверка: {{ date(report.checked_at) }}</p>
        <p data-testid="audit-coverage">{{ report.coverage.complete ? 'Весь текст DOCX прочитан.' : 'Прочитан не весь текст DOCX; изменения заблокированы.' }} Полнота извлечения не подтверждает соответствие законодательству.</p>
        <p v-if="report.coverage.requires_visual_review" class="mt-2 text-amber-800 dark:text-amber-200">В шаблоне есть изображения или другие нетекстовые элементы. Проверьте их на всех страницах полного PDF: текстовый анализ их не оценивает.</p>
        <p v-for="message in coverageMessages" :key="message" class="text-amber-800 dark:text-amber-200">{{ message }}</p>
        <p class="mt-2 text-amber-800 dark:text-amber-200">{{ report.legal_currency === 'changed' ? 'Источники права изменились — нужна новая проверка.' : report.legal_currency === 'matches_supplied_hash' ? 'Набор источников совпадает с сохранённым при проверке. Актуальность законодательства проверяется отдельно.' : 'Актуальность законодательства требует внешней повторной проверки.' }}</p>
        <div v-if="report.stale" class="mt-3 rounded-lg bg-amber-100 p-3 text-amber-950" role="status" data-testid="audit-stale">
          <p class="font-semibold">Отчёт устарел. Сохранение решений, предпросмотр и активация заблокированы.</p>
          <p v-for="reason in report.stale_reasons" :key="reason">{{ label(reason) }}</p>
        </div>
        <details v-if="Object.keys(report.checklist).length" class="mt-3"><summary class="cursor-pointer font-semibold">Области проверки</summary><ul class="mt-2 list-inside list-disc"><li v-for="(state, name) in report.checklist" :key="name">{{ label(name) }}: {{ label(state) }}</li></ul></details>
        <button type="button" class="settings-button-secondary mt-3" :disabled="busy" @click="downloadSource(report.version_id)">Скачать исходный шаблон DOCX</button>
        <details class="mt-3 text-xs text-slate-500" data-testid="audit-report-technical"><summary class="cursor-pointer">Технические сведения</summary><pre class="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all">{{ technicalText({ report_id: report.id, template_id: report.template_id, version_id: report.version_id, revision: report.revision, source_hash: report.source_hash, context_hash: report.context_hash, legal_sources_hash: report.legal_sources_hash, coverage: report.coverage }) }}</pre></details>
      </div>

      <article v-for="(finding, findingIndex) in report.findings" :key="finding.id" class="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700" :data-testid="`audit-finding-${finding.id}`">
        <div class="flex flex-wrap gap-2 text-xs font-semibold"><span>{{ label(finding.category) }}</span><span>Важность: {{ label(finding.severity) }}</span><span>Уверенность: {{ label(finding.confidence) }}</span><span>{{ label(finding.status) }}</span></div>
        <p v-if="finding.decision_current === false" class="text-sm text-amber-800 dark:text-amber-200" role="status">Решение относится к прежней редакции или источникам. Проверьте и сохраните решение заново.</p>
        <p :class="finding.verification === 'verified' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-800 dark:text-amber-200'" class="text-sm font-semibold">{{ finding.verification === 'verified' ? 'Проверено в рамках отчёта' : finding.verification === 'needs_legal_review' ? 'Нужна проверка юриста' : 'Юридически не проверено' }}</p>
        <p class="text-sm"><strong>Риск и причина:</strong> {{ finding.risk }}</p>
        <p class="text-sm"><strong>Применимость:</strong> {{ finding.applicability }}</p>
        <div class="grid gap-3 md:grid-cols-2"><div class="min-w-0 rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><h3 class="text-xs font-semibold text-slate-500">Исходная формулировка · {{ findingLocation(finding) }}</h3><p class="mt-2 whitespace-pre-wrap break-words text-sm">{{ finding.original_text }}</p></div><div class="min-w-0 rounded-lg bg-brand-50 p-3 dark:bg-brand-950/30"><h3 class="text-xs font-semibold text-brand-700 dark:text-brand-300">Предлагаемая формулировка</h3><p class="mt-2 whitespace-pre-wrap break-words text-sm">{{ finding.proposed_text ?? 'Замена не предложена' }}</p></div></div>
        <details v-if="finding.occurrences?.length" class="text-sm">
          <summary class="cursor-pointer font-semibold">Вхождения и контекст (всего {{ finding.occurrences_total ?? finding.occurrences.length }})</summary>
          <div v-for="(occurrence, index) in finding.occurrences" :key="`${occurrence.block_id}-${index}`" class="mt-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><p class="text-xs text-slate-500">{{ occurrence.location_label || locationLabel(occurrence.part, occurrence.location) }}</p><p class="mt-1 whitespace-pre-wrap break-words">{{ occurrence.text }}</p></div>
          <div v-if="finding.occurrences_next_page || (finding.occurrences_page || 1) > 1" class="mt-3 flex flex-wrap items-center gap-3"><span class="text-xs text-slate-500">Страница {{ finding.occurrences_page || 1 }} · показаны фрагменты вокруг совпадений</span><button v-if="(finding.occurrences_page || 1) > 1" type="button" class="settings-button-secondary" :disabled="busy" @click="loadOccurrences(finding, (finding.occurrences_page || 1) - 1)">Предыдущие вхождения</button><button v-if="finding.occurrences_next_page" type="button" class="settings-button-secondary" :disabled="busy" @click="loadOccurrences(finding)">Следующие вхождения</button></div>
        </details>
        <details v-if="finding.sources?.length" class="text-sm"><summary class="cursor-pointer font-semibold">Источники права ({{ finding.sources.length }})</summary><article v-for="(source, index) in finding.sources" :key="index" class="mt-3 space-y-1 rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p><a v-if="sourceUrl(source.url)" :href="sourceUrl(source.url)" target="_blank" rel="noopener noreferrer" class="font-semibold text-brand-700 underline dark:text-brand-300">{{ source.title }}</a><span v-else>{{ source.title }}</span> · {{ source.provision }}</p><p class="font-semibold" :class="source.verification === 'verified' && source.official ? 'text-emerald-700' : 'text-amber-800 dark:text-amber-200'">{{ source.official ? 'Официальный источник' : 'Неофициальный источник' }} · {{ source.verification === 'verified' ? 'проверен' : source.verification === 'future' ? 'будущая редакция' : source.verification === 'unavailable' ? 'недоступен для проверки' : 'не проверен' }}</p><p class="whitespace-pre-wrap break-words">{{ source.excerpt }}</p><p>Редакция: {{ source.edition }}. Действует с {{ source.effective_from }}{{ source.effective_until ? ` по ${source.effective_until}` : '' }}. Проверен {{ date(source.checked_at) }}.</p><p>Применимость: {{ source.applicability }}</p></article></details>
        <p v-else class="text-sm text-amber-800 dark:text-amber-200">Источники права не приложены.</p>
        <form v-if="decisions[finding.id]" class="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-3 dark:border-slate-700" @submit.prevent="decide(finding)">
          <label class="settings-field"><span>Решение</span><select v-model="decisions[finding.id]!.status" class="settings-input" :disabled="locked || busy" :aria-label="`Решение по замечанию ${findingIndex + 1}`"><option v-for="option in decisionOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          <label class="settings-field min-w-0 flex-1"><span>Основание решения</span><input v-model="decisions[finding.id]!.reason" class="settings-input" :disabled="locked || busy" :aria-label="`Основание решения ${findingIndex + 1}`" maxlength="3000" required /></label>
          <button type="submit" class="settings-button-secondary" :disabled="locked || busy || !decisions[finding.id]?.reason.trim()">Сохранить решение</button>
        </form>
        <details class="text-xs text-slate-500"><summary class="cursor-pointer">Технические сведения</summary><p class="mt-2 break-all">{{ finding.block_id }}</p><p v-for="(occurrence, index) in finding.occurrences || []" :key="index" class="mt-1 break-all">{{ occurrence.block_id }} · {{ occurrence.part }} · {{ technicalText(occurrence.location) }}</p></details>
        <details v-if="finding.decision_history?.length" class="text-sm"><summary class="cursor-pointer font-semibold">История решений</summary><p v-for="(entry, index) in finding.decision_history" :key="index" class="mt-2 break-words">{{ label(String(entry.from || '')) }} → {{ label(String(entry.to || '')) }} · {{ entry.at ? date(String(entry.at)) : '' }}<br />{{ entry.reason }}</p></details>
      </article>
      <p v-if="!report.findings.length" class="text-sm text-slate-500">Замечаний в этом отчёте нет.</p>

      <section v-if="report.proposals.length" class="space-y-4 border-t border-slate-200 pt-5 dark:border-slate-700">
        <h3 class="text-lg font-bold">Предлагаемая версия шаблона</h3>
        <label class="settings-field"><span>Версия для сравнения</span><select v-model="selectedProposalId" class="settings-input" :disabled="busy"><option v-for="item in report.proposals" :key="item.id" :value="item.id">{{ item.version_number ? `Версия ${item.version_number}` : 'Предложение' }} · {{ label(item.status) }} · {{ date(item.created_at) }}</option></select></label>
        <div v-if="proposal" class="space-y-4">
          <p v-if="proposal.stale" class="rounded-lg bg-amber-100 p-3 text-sm text-amber-950">Предлагаемая версия устарела: изменились условия или источники права. Требуется новое предложение.</p>
          <div v-for="(edit, index) in proposal.edits" :key="index" class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"><p class="break-all text-xs text-slate-500">{{ report.findings.find(item => item.id === edit.finding_id) ? findingLocation(report.findings.find(item => item.id === edit.finding_id)!) : 'Фрагмент шаблона' }}</p><div class="mt-2 grid gap-3 md:grid-cols-2"><div class="min-w-0"><p class="text-xs font-semibold text-slate-500">Было</p><p class="whitespace-pre-wrap break-words text-sm">{{ edit.expected_text }}</p></div><div class="min-w-0"><p class="text-xs font-semibold text-brand-700 dark:text-brand-300">Предлагается</p><p class="whitespace-pre-wrap break-words text-sm">{{ edit.replacement_text }}</p></div></div><p class="mt-3 text-sm"><strong>Причина:</strong> {{ edit.reason }}</p></div>
          <details class="text-xs text-slate-500"><summary class="cursor-pointer">Технические сведения</summary><pre class="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all">{{ technicalText({ proposal_id: proposal.id, version_id: proposal.version_id, source_hash: proposal.source_hash, edits: proposal.edits.map(item => ({ finding_id: item.finding_id, block_id: item.block_id })) }) }}</pre></details>
          <div class="flex flex-wrap gap-2"><button type="button" class="settings-button-secondary" :disabled="busy" @click="downloadSource(proposal.version_id)">Скачать предлагаемый шаблон DOCX</button><button type="button" class="settings-button-secondary" :disabled="proposalLocked || busy || proposal.status !== 'draft'" @click="loadContext">Подготовить учебный пример</button></div>
          <p class="text-sm text-slate-500">Предпросмотр использует вымышленные данные. Для проверки полей оставьте нужные реквизиты пустыми. Существующие черновики и выпущенные документы клиентов не изменяются.</p>
          <div v-if="context" class="space-y-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-800" data-testid="audit-preview-context">
            <p class="text-sm font-semibold" data-testid="audit-preview-scenario">{{ previewScenarioLabel }}</p>
            <div class="flex flex-wrap items-end gap-4"><label class="settings-field"><span>Клиент в учебном примере</span><select v-model="customerType" class="settings-input" :disabled="busy" data-testid="audit-customer-type" @change="applyScenario"><option value="individual">Физлицо</option><option value="organization">Организация</option><option value="individual_entrepreneur">ИП</option></select></label><label class="flex min-h-10 items-center gap-2 text-sm"><input v-model="vat" type="checkbox" :disabled="busy" data-testid="audit-vat" @change="applyScenario" />Продавец платит НДС</label></div>
            <fieldset v-if="Object.keys(context.values).length" class="space-y-3" data-testid="audit-context-fields">
              <legend class="text-sm font-semibold">Учебные реквизиты</legend>
              <p class="text-xs text-slate-500">Измените пример или очистите поле, чтобы проверить документ без этого реквизита.</p>
              <div class="grid gap-3 sm:grid-cols-2">
                <div v-for="(_, name, index) in context.values" :key="name" class="min-w-0 space-y-1">
                  <label class="settings-field"><span>{{ fieldLabel(name, index) }}</span><textarea v-model="context.values[name]" class="settings-input h-auto py-2" rows="2" :disabled="busy" :aria-label="fieldLabel(name, index)" :data-testid="`audit-context-field-${name}`" /></label>
                  <button type="button" class="text-xs font-semibold text-brand-700 disabled:opacity-50 dark:text-brand-300" :disabled="busy || (!context.values[name] && !exampleValues[name])" :aria-label="`${context.values[name] ? 'Очистить' : 'Вернуть пример'}: ${fieldLabel(name, index)}`" @click="toggleEmpty(name)">{{ context.values[name] ? 'Очистить поле' : 'Вернуть пример' }}</button>
                </div>
              </div>
            </fieldset>
            <fieldset v-if="additionalConditions.length" class="space-y-3" data-testid="audit-context-conditions">
              <legend class="text-sm font-semibold">Условия документа</legend>
              <div class="grid gap-3 sm:grid-cols-2"><label v-for="(name, index) in additionalConditions" :key="name" class="flex items-start gap-2 text-sm"><input v-model="context.conditions[name]" type="checkbox" class="mt-1" :disabled="busy" :aria-label="conditionLabel(name, index)" />{{ conditionLabel(name, index) }}</label></div>
            </fieldset>
            <fieldset v-for="(rows, name, tableIndex) in context.table_rows" :key="name" class="space-y-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700" :data-testid="`audit-context-table-${name}`">
              <legend class="px-1 text-sm font-semibold">{{ tableLabel(name, tableIndex) }}</legend>
              <div v-for="(row, rowIndex) in rows" :key="rowIndex" class="space-y-2 rounded-lg bg-white p-3 dark:bg-slate-900">
                <div class="flex items-center justify-between gap-2"><h4 class="text-xs font-semibold">Строка {{ rowIndex + 1 }}</h4><button type="button" class="text-xs font-semibold text-red-700 disabled:opacity-50 dark:text-red-300" :disabled="busy" :aria-label="`Убрать строку ${rowIndex + 1}: ${tableLabel(name, tableIndex)}`" @click="rows.splice(rowIndex, 1)">Убрать строку</button></div>
                <div class="grid gap-3 sm:grid-cols-2"><label v-for="(_, fieldName, fieldIndex) in row" :key="fieldName" class="settings-field"><span>{{ rowFieldLabel(fieldName, fieldIndex) }}</span><input v-model="row[fieldName]" class="settings-input" :disabled="busy" :aria-label="`${rowFieldLabel(fieldName, fieldIndex)}, строка ${rowIndex + 1}: ${tableLabel(name, tableIndex)}`" /></label></div>
              </div>
              <button type="button" class="settings-button-secondary" :disabled="busy" @click="addRow(name)">Добавить строку</button>
            </fieldset>
            <details class="text-xs text-slate-500"><summary class="cursor-pointer">Технические сведения</summary><pre class="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all">{{ technicalText(context) }}</pre></details>
            <div class="flex flex-wrap gap-2"><button type="button" class="settings-button-primary" :disabled="proposalLocked || busy" data-testid="audit-preview-pdf" @click="renderPreview('pdf')">Открыть полный PDF</button><button type="button" class="settings-button-secondary" :disabled="proposalLocked || busy" @click="renderPreview('docx')">Скачать учебный DOCX</button></div>
          </div>
          <div v-if="pdfUrl" class="space-y-2" data-testid="audit-full-pdf"><a :href="pdfUrl" target="_blank" rel="noopener" class="text-sm font-semibold text-brand-700 underline dark:text-brand-300">Открыть PDF в отдельной вкладке</a><iframe :src="pdfUrl" title="Полный PDF предлагаемой версии на вымышленных данных" class="h-[75vh] min-h-96 w-full rounded-xl border border-slate-200 bg-white" /></div>
          <div class="space-y-2 rounded-xl border border-amber-200 p-4 dark:border-amber-800"><p class="text-sm">Активация меняет шаблон для будущих документов. Перед активацией откройте полный PDF и проверьте нужные условия и страницы.</p><button type="button" class="settings-button-primary" :disabled="!canActivate" data-testid="audit-activate" @click="activate">Сделать предлагаемую версию активной</button><p v-if="proposal.status !== 'draft'" class="text-xs text-slate-500">Текущее состояние версии: {{ label(proposal.status) }}.</p><p v-else-if="!previewedProposal" class="text-xs text-slate-500">Активация станет доступна после подготовки полного PDF.</p></div>
        </div>
      </section>
    </div>
  </section>
</template>
