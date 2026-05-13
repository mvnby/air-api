<script setup lang="ts">
import { computed, ref } from 'vue';

type ConditionMode = 'contract' | 'invoice';
type ConditionPreset = {
  id: string;
  title: string;
  text: string;
};
type ConditionGroup = {
  id: string;
  title: string;
  mode: ConditionMode;
  presets: ConditionPreset[];
};

const props = withDefaults(defineProps<{
  modelValue: string;
  saving?: boolean;
  saveDisabled?: boolean;
  showSave?: boolean;
}>(), {
  modelValue: '',
  saving: false,
  saveDisabled: false,
  showSave: false,
});

const emit = defineEmits<{
  'update:modelValue': [value: string];
  save: [];
}>();

const activeMode = ref<ConditionMode>('contract');
const expandedGroupIds = ref<Set<string>>(new Set());

const conditionGroups: ConditionGroup[] = [
  {
    id: 'universal',
    title: 'Универсальные',
    mode: 'contract',
    presets: [
      {
        id: 'access',
        title: 'Доступ к оборудованию',
        text: 'Заказчик обязан обеспечить свободный и безопасный доступ к оборудованию и месту проведения работ.',
      },
      {
        id: 'lifts',
        title: 'Вышка / леса / альпинисты',
        text: 'Прокат, сборка и разборка строительных лесов, услуги автовышки и промышленных альпинистов не входят в стоимость работ и оплачиваются отдельно либо предоставляются Заказчиком.',
      },
      {
        id: 'extra-works',
        title: 'Дополнительные работы',
        text: 'Работы и материалы, не указанные в настоящем договоре, выполняются по дополнительному согласованию Сторон и оплачиваются отдельно.',
      },
      {
        id: 'email-approval',
        title: 'Согласование по переписке',
        text: 'Согласование дополнительных работ, материалов и сроков допускается посредством электронной переписки.',
      },
    ],
  },
  {
    id: 'installation',
    title: 'Монтаж',
    mode: 'contract',
    presets: [
      {
        id: 'route-meters',
        title: 'Дополнительные метры трассы',
        text: 'Дополнительные метры межблочной трассы, декоративный короб, кронштейны, дренажные материалы, электрический кабель и иные материалы сверх согласованного объема оплачиваются отдельно.',
      },
      {
        id: 'hidden-utilities',
        title: 'Скрытые коммуникации',
        text: 'Исполнитель не несет ответственности за скрытые коммуникации, кабели, трубы и иные элементы, не обозначенные Заказчиком до начала работ.',
      },
      {
        id: 'customer-equipment',
        title: 'Оборудование заказчика',
        text: 'Оборудование и материалы, предоставленные Заказчиком, используются Исполнителем без гарантии на их качество, комплектность и работоспособность. Гарантия Исполнителя распространяется только на выполненные работы.',
      },
      {
        id: 'winter-kit',
        title: 'Низкотемпературный комплект',
        text: 'Работа оборудования при отрицательных температурах наружного воздуха возможна только в пределах технических характеристик оборудования и установленного низкотемпературного комплекта.',
      },
    ],
  },
  {
    id: 'repair',
    title: 'Ремонт',
    mode: 'contract',
    presets: [
      {
        id: 'hidden-defects',
        title: 'Скрытые дефекты',
        text: 'В процессе диагностики или ремонта могут быть выявлены скрытые дефекты либо дополнительные неисправности, не определяемые при первоначальном осмотре оборудования.',
      },
      {
        id: 'repair-impossible',
        title: 'Невозможность ремонта',
        text: 'Исполнитель не гарантирует возможность полного восстановления работоспособности оборудования при значительном износе, коррозии, множественных утечках, повреждении основных узлов либо отсутствии необходимых запасных частей.',
      },
      {
        id: 'repair-not-worth',
        title: 'Нерентабельный ремонт',
        text: 'При выявлении экономической нецелесообразности ремонта Исполнитель вправе приостановить работы и уведомить Заказчика о возможных вариантах дальнейших действий.',
      },
      {
        id: 'refrigerant-fact',
        title: 'Хладагент по факту',
        text: 'Стоимость хладагента, расходных материалов и комплектующих определяется по фактическому объему использованных материалов и может быть уточнена по результатам выполнения работ.',
      },
    ],
  },
  {
    id: 'maintenance',
    title: 'ТО',
    mode: 'contract',
    presets: [
      {
        id: 'maintenance-not-repair',
        title: 'ТО не ремонт',
        text: 'Техническое обслуживание не является ремонтом оборудования и не включает устранение неисправностей, замену комплектующих, дозаправку хладагента и выполнение ремонтных работ, если иное не согласовано Сторонами отдельно.',
      },
      {
        id: 'maintenance-no-breakdown-guarantee',
        title: 'Не гарантия отсутствия поломок',
        text: 'Исполнитель не гарантирует отсутствие неисправностей оборудования, связанных с его техническим состоянием, износом либо скрытыми дефектами, выявление которых не входило в состав выполняемых работ по техническому обслуживанию.',
      },
      {
        id: 'repair-separately',
        title: 'Ремонт отдельно',
        text: 'В случае выявления неисправностей либо необходимости проведения ремонтных работ Исполнитель уведомляет Заказчика отдельно. Ремонтные работы выполняются по дополнительному согласованию Сторон.',
      },
    ],
  },
  {
    id: 'invoice',
    title: 'Счет',
    mode: 'invoice',
    presets: [
      {
        id: 'invoice-lifts',
        title: 'Вышка / леса / альпинисты',
        text: 'Автовышка, леса и промышленный альпинизм в стоимость не входят.',
      },
      {
        id: 'invoice-extra-works',
        title: 'Дополнительные работы',
        text: 'Дополнительные материалы и работы оплачиваются отдельно по факту согласования.',
      },
      {
        id: 'invoice-repair-price',
        title: 'Ремонт после диагностики',
        text: 'Стоимость ремонта может быть уточнена после диагностики.',
      },
      {
        id: 'invoice-maintenance',
        title: 'ТО без ремонта',
        text: 'Техническое обслуживание не включает ремонт и замену комплектующих.',
      },
      {
        id: 'invoice-route',
        title: 'Трасса сверх объема',
        text: 'Длина трассы сверх согласованного объема оплачивается отдельно.',
      },
    ],
  },
];

const normalizedLine = (value: string) => value.replace(/\s+/g, ' ').trim();
const lines = computed(() => props.modelValue.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
const selectedLineSet = computed(() => new Set(lines.value.map(normalizedLine)));
const visibleGroups = computed(() => conditionGroups.filter((group) => group.mode === activeMode.value));
const selectedCount = computed(() => (
  conditionGroups.reduce((count, group) => (
    count + group.presets.filter((preset) => selectedLineSet.value.has(normalizedLine(preset.text))).length
  ), 0)
));

const selectedCountForGroup = (group: ConditionGroup) => (
  group.presets.filter((preset) => selectedLineSet.value.has(normalizedLine(preset.text))).length
);

const updateLines = (nextLines: string[]) => {
  emit('update:modelValue', nextLines.join('\n'));
};

const isSelected = (preset: ConditionPreset) => selectedLineSet.value.has(normalizedLine(preset.text));
const isGroupExpanded = (groupId: string) => expandedGroupIds.value.has(groupId);

const toggleGroup = (groupId: string) => {
  const next = new Set(expandedGroupIds.value);
  if (next.has(groupId)) {
    next.delete(groupId);
  } else {
    next.add(groupId);
  }
  expandedGroupIds.value = next;
};

const togglePreset = (preset: ConditionPreset) => {
  if (isSelected(preset)) {
    const removeKey = normalizedLine(preset.text);
    updateLines(lines.value.filter((line) => normalizedLine(line) !== removeKey));
    return;
  }
  updateLines([...lines.value, preset.text]);
};

const clearSelected = () => {
  const presetKeys = new Set(
    conditionGroups.flatMap((group) => group.presets.map((preset) => normalizedLine(preset.text)))
  );
  updateLines(lines.value.filter((line) => !presetKeys.has(normalizedLine(line))));
};
</script>

<template>
  <div class="mb-3 rounded-xl border border-slate-200 bg-white/80 p-3 shadow-sm dark:border-slate-700/50 dark:bg-slate-900/40 dark:shadow-none">
    <div class="mb-3 flex flex-wrap items-start justify-between gap-3">
      <div>
        <label class="block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Дополнительные условия</label>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {{ saving ? 'Сохраняю перед генерацией...' : 'Выбранные строки сохранятся перед созданием документа.' }}
        </p>
      </div>
      <button
        v-if="showSave"
        type="button"
        class="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-50"
        :disabled="saveDisabled || saving"
        @click="emit('save')"
      >
        {{ saving ? 'Сохраняю...' : 'Сохранить' }}
      </button>
    </div>

    <div class="mb-3 inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs dark:border-slate-700 dark:bg-slate-800/70">
      <button
        type="button"
        class="rounded-md px-3 py-1.5 font-semibold transition"
        :class="activeMode === 'contract' ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white' : 'text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'"
        @click="activeMode = 'contract'"
      >
        Договор
      </button>
      <button
        type="button"
        class="rounded-md px-3 py-1.5 font-semibold transition"
        :class="activeMode === 'invoice' ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white' : 'text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'"
        @click="activeMode = 'invoice'"
      >
        Счет
      </button>
    </div>

    <div class="space-y-3">
      <section v-for="group in visibleGroups" :key="group.id">
        <button
          type="button"
          class="mb-2 flex w-full items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left md:pointer-events-none md:border-0 md:bg-transparent md:px-0 md:py-0 dark:border-slate-700 dark:bg-slate-800 md:dark:bg-transparent"
          :aria-expanded="isGroupExpanded(group.id)"
          @click="toggleGroup(group.id)"
        >
          <span class="flex min-w-0 items-center gap-2">
            <span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ group.title }}</span>
            <span
              v-if="selectedCountForGroup(group)"
              class="rounded-full bg-teal-100 px-2 py-0.5 text-[11px] font-semibold text-teal-700 dark:bg-teal-500/15 dark:text-teal-200"
            >
              {{ selectedCountForGroup(group) }}
            </span>
          </span>
          <span class="material-icons-round text-[18px] text-slate-500 md:hidden">
            {{ isGroupExpanded(group.id) ? 'expand_less' : 'expand_more' }}
          </span>
        </button>
        <div
          class="gap-2 md:grid md:grid-cols-2"
          :class="isGroupExpanded(group.id) ? 'grid' : 'hidden'"
        >
          <button
            v-for="preset in group.presets"
            :key="preset.id"
            type="button"
            class="min-h-[86px] rounded-lg border px-3 py-2 text-left transition"
            :class="isSelected(preset)
              ? 'border-teal-400 bg-teal-50 text-teal-950 dark:border-teal-500/60 dark:bg-teal-500/10 dark:text-teal-100'
              : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-teal-500/50'"
            @click="togglePreset(preset)"
          >
            <span class="flex items-start gap-2">
              <span
                class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[12px]"
                :class="isSelected(preset) ? 'border-teal-500 bg-teal-500 text-white' : 'border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-900'"
              >
                <span v-if="isSelected(preset)" class="material-icons-round text-[12px]">check</span>
              </span>
              <span class="min-w-0">
                <span class="block text-sm font-semibold leading-snug">{{ preset.title }}</span>
                <span class="mt-1 line-clamp-2 block text-xs leading-snug text-slate-500 dark:text-slate-400">{{ preset.text }}</span>
              </span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div class="mt-3 space-y-2">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span class="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Итоговый текст</span>
        <button
          v-if="selectedCount"
          type="button"
          class="text-xs font-semibold text-slate-500 hover:text-red-600 dark:text-slate-400 dark:hover:text-red-300"
          @click="clearSelected"
        >
          Убрать выбранные
        </button>
      </div>
      <textarea
        :value="modelValue"
        rows="5"
        class="w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        placeholder="Редкое условие можно вписать вручную"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      />
      <p class="text-xs text-slate-500 dark:text-slate-400">В нумерованном пункте договора каждая строка станет отдельным пунктом.</p>
    </div>
  </div>
</template>
