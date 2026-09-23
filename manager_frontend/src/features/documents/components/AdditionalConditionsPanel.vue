<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { ManagerDocumentSystemService, type ConditionPresetItem } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { confirmDialog } from '../../../services/ui-feedback';
import type { BusinessDocumentTerms } from '../model/business-document-terms';

type Preset = { id: string; label: string; text: string };
const builtInPresets: Preset[] = [
  { id: 'access', label: 'Доступ к оборудованию', text: 'Заказчик обеспечивает свободный и безопасный доступ к оборудованию и месту проведения работ.' },
  { id: 'extra-works', label: 'Дополнительные работы', text: 'Работы и материалы вне согласованного объёма выполняются по дополнительному согласованию и оплачиваются отдельно.' },
  { id: 'hidden-utilities', label: 'Скрытые коммуникации', text: 'Исполнитель не отвечает за скрытые коммуникации, не обозначенные Заказчиком до начала работ.' },
  { id: 'customer-equipment', label: 'Оборудование заказчика', text: 'Гарантия Исполнителя распространяется на выполненные работы, но не на качество и комплектность оборудования Заказчика.' },
  { id: 'email-approval', label: 'Согласование по переписке', text: 'Дополнительные работы, материалы и сроки могут согласовываться сторонами по электронной переписке.' },
  { id: 'hidden-defects', label: 'Скрытые дефекты', text: 'В процессе диагностики или ремонта могут выявиться скрытые дефекты, не определяемые при первоначальном осмотре.' },
  { id: 'access-equipment', label: 'Леса и альпинисты', text: 'Строительные леса, услуги промышленных альпинистов и специальная подъёмная техника не входят в стандартную стоимость работ и согласовываются отдельно.' },
];

const props = defineProps<{ terms: BusinessDocumentTerms; orderConditions?: string | null; embedded?: boolean }>();
const emit = defineEmits<{ updateTerms: [terms: BusinessDocumentTerms] }>();
const savedPresets = ref<ConditionPresetItem[]>([]);
const saving = ref(false);
const notice = ref('');
onMounted(async () => {
  try {
    const loaded = (await ManagerDocumentSystemService.listManagerDocumentConditionPresets()).items;
    savedPresets.value = [
      ...savedPresets.value,
      ...loaded.filter((item) => !savedPresets.value.some((saved) => saved.id === item.id)),
    ];
  } catch (error) {
    notice.value = `Не удалось загрузить сохранённые условия: ${getApiErrorMessage(error)}`;
  }
});
const normalized = (value: string) => value.replace(/\s+/g, ' ').trim();
const lines = () => (props.terms.additional_conditions || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
const selected = (preset: Preset) => lines().some((line) => normalized(line) === normalized(preset.text));
const update = (nextLines: string[]) => emit('updateTerms', {
  ...props.terms,
  additional_conditions: nextLines.length ? nextLines.join('\n') : null,
  additional_conditions_overridden: true,
});
const toggle = (preset: Preset) => {
  const current = lines();
  update(selected(preset) ? current.filter((line) => normalized(line) !== normalized(preset.text)) : [...current, preset.text]);
};
const updateText = (event: Event) => {
  const value = (event.target as HTMLTextAreaElement).value.trim();
  emit('updateTerms', {
    ...props.terms,
    additional_conditions: value || null,
    additional_conditions_overridden: true,
  });
};
const saveLastCondition = async () => {
  const currentLines = lines();
  const text = currentLines[currentLines.length - 1];
  if (!text || saving.value) return;
  saving.value = true;
  notice.value = '';
  try {
    const item = await ManagerDocumentSystemService.createManagerDocumentConditionPreset({ text });
    savedPresets.value = [item, ...savedPresets.value];
    notice.value = 'Условие сохранено для будущих документов.';
  } catch (error) {
    notice.value = getApiErrorMessage(error);
  } finally {
    saving.value = false;
  }
};
const removePreset = async (item: ConditionPresetItem) => {
  if (!await confirmDialog({
    title: 'Удалить сохранённое условие?',
    description: 'Плашка исчезнет у менеджеров организации. Уже созданные документы не изменятся.',
    confirmText: 'Удалить',
    variant: 'danger',
  })) return;
  try {
    await ManagerDocumentSystemService.deleteManagerDocumentConditionPreset(item.id);
    savedPresets.value = savedPresets.value.filter((preset) => preset.id !== item.id);
  } catch (error) {
    notice.value = getApiErrorMessage(error);
  }
};
</script>

<template>
  <section :class="embedded ? 'mt-2' : 'business-section'" data-testid="additional-conditions-panel">
    <p class="business-help">Условия заказа можно использовать как есть или дополнить для этого документа.</p>
    <div class="mt-3 inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800" data-testid="additional-conditions-source-toggle"><button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="!terms.additional_conditions_overridden ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300'" :aria-pressed="!terms.additional_conditions_overridden" @click="emit('updateTerms', { ...terms, additional_conditions: null, additional_conditions_overridden: false })">Из заказа</button><button type="button" class="rounded-lg px-3 py-1.5 text-sm font-semibold transition" :class="terms.additional_conditions_overridden ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300'" :aria-pressed="terms.additional_conditions_overridden" @click="emit('updateTerms', { ...terms, additional_conditions_overridden: true })">Свой текст</button></div>
    <p v-if="!terms.additional_conditions_overridden" class="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300" data-testid="order-conditions-preview">{{ orderConditions?.trim() || 'В заказе дополнительные условия не указаны.' }}</p>
    <div v-if="terms.additional_conditions_overridden" class="mt-3 flex flex-wrap gap-2">
      <span v-for="item in savedPresets" :key="`saved-${item.id}`" class="inline-flex items-center rounded-lg border border-brand-300 bg-brand-50 dark:bg-brand-950/30"><button type="button" class="condition-chip border-0" :aria-pressed="selected({ id: String(item.id), label: item.text, text: item.text })" @click="toggle({ id: String(item.id), label: item.text, text: item.text })">{{ item.text.length > 38 ? `${item.text.slice(0, 38)}…` : item.text }}</button><button class="mr-1 rounded px-1 text-sm text-slate-500 hover:text-rose-700" type="button" :aria-label="`Удалить условие ${item.text}`" @click="removePreset(item)">×</button></span>
      <button v-for="preset in builtInPresets" :key="preset.id" type="button" class="condition-chip" :class="selected(preset) ? 'condition-chip-active' : 'condition-chip-idle'" :aria-pressed="selected(preset)" @click="toggle(preset)">{{ preset.label }}</button>
    </div>
    <label v-if="terms.additional_conditions_overridden" class="business-field mt-3"><span>Текст условий</span><textarea :value="terms.additional_conditions || ''" class="business-input min-h-28 py-2" placeholder="Каждое условие — с новой строки" @input="updateText" /></label>
    <div v-if="terms.additional_conditions_overridden" class="mt-2 flex flex-wrap items-center gap-2"><button class="text-xs font-semibold text-brand-700 underline disabled:opacity-50" type="button" data-testid="save-condition-preset" :disabled="!lines().length || saving" @click="saveLastCondition">Сохранить последнее условие как плашку</button><span class="text-xs text-slate-500">Плашка будет доступна менеджерам вашей организации.</span></div>
    <p v-if="notice" class="mt-2 text-xs text-slate-600" role="status">{{ notice }}</p>
  </section>
</template>

<style scoped>
.business-section { @apply mt-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/50; }
.business-heading { @apply text-sm font-bold text-slate-900 dark:text-white; }
.business-help { @apply mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400; }
.business-field { @apply flex min-w-0 flex-col gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200; }
.business-input { @apply h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-white; }
.condition-chip { @apply rounded-lg border px-3 py-2 text-xs font-semibold transition; }
.condition-chip-active { @apply border-brand-600 bg-brand-600 text-white; }
.condition-chip-idle { @apply border-slate-200 bg-slate-50 text-slate-700 hover:border-brand-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200; }
</style>
