<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { ArrowRight, Check, ChevronDown, Clock3, MoreVertical, Pause, Pencil, Play, Save, Trash2, Undo2, X } from 'lucide-vue-next';
import { formatMoney } from './order-utils';
import { ORDER_WORKFLOW_OPTIONS, type OrderWorkflowType, type OrderWorkspaceViewModel } from './order-workspace';
import { STICKY_HEADER_RESIZE_DURATION_MS } from '../../composables/useSmartStickyHeader';

const props = defineProps<{
  orderId?: number;
  title: string;
  customerName?: string;
  workflow: OrderWorkflowType;
  viewModel: OrderWorkspaceViewModel;
  total: number;
  paid: number;
  balance: number;
  isWebsiteOrder?: boolean;
  isOnHold?: boolean;
  dirty?: boolean;
  saving?: boolean;
  compact?: boolean;
}>();

const emit = defineEmits<{
  'update:title': [value: string];
  'change-workflow': [value: OrderWorkflowType];
  next: [];
  payments: [];
  hold: [];
  delete: [];
  discard: [];
  save: [];
  close: [];
}>();

const editingTitle = ref(false);
const menuOpen = ref(false);
const titleDraft = ref('');
const headerRef = ref<HTMLElement | null>(null);
const contentRef = ref<HTMLElement | null>(null);
const focusLocksCompactMode = ref(false);
const effectiveCompact = computed(() => Boolean(props.compact && !editingTitle.value && !menuOpen.value && !focusLocksCompactMode.value));
const showCustomerName = computed(() => {
  const customerName = String(props.customerName || '').trim();
  return Boolean(effectiveCompact.value && customerName && customerName !== String(props.title || '').trim());
});
let resizeAnimation: Animation | null = null;
let contentAnimation: Animation | null = null;
let resizeGeneration = 0;

const clearResizeAnimation = () => {
  resizeGeneration += 1;
  resizeAnimation?.cancel();
  resizeAnimation = null;
  contentAnimation?.cancel();
  contentAnimation = null;
  headerRef.value?.style.removeProperty('overflow');
};

watch(effectiveCompact, async (isCompact) => {
  const header = headerRef.value;
  if (!header) return;
  const generation = ++resizeGeneration;
  const fromHeight = header.getBoundingClientRect().height;
  resizeAnimation?.cancel();
  resizeAnimation = null;
  contentAnimation?.cancel();
  contentAnimation = null;
  header.style.removeProperty('overflow');

  await nextTick();
  if (generation !== resizeGeneration || headerRef.value !== header) return;
  const toHeight = header.getBoundingClientRect().height;
  if (
    Math.abs(toHeight - fromHeight) < 1
    || window.matchMedia('(prefers-reduced-motion: reduce)').matches
    || typeof header.animate !== 'function'
  ) return;

  header.style.overflow = 'hidden';
  const animation = header.animate(
    [{ height: `${fromHeight}px` }, { height: `${toHeight}px` }],
    {
      duration: STICKY_HEADER_RESIZE_DURATION_MS,
      easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
    },
  );
  resizeAnimation = animation;
  const content = contentRef.value;
  if (content && typeof content.animate === 'function') {
    contentAnimation = content.animate(
      [
        {
          opacity: 0.68,
          transform: `translateY(${isCompact ? '10px' : '-10px'})`,
        },
        { opacity: 1, transform: 'translateY(0)' },
      ],
      {
        duration: Math.round(STICKY_HEADER_RESIZE_DURATION_MS * 0.82),
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    );
    const activeContentAnimation = contentAnimation;
    activeContentAnimation.addEventListener('finish', () => {
      if (contentAnimation === activeContentAnimation) contentAnimation = null;
    }, { once: true });
  }
  animation.addEventListener('finish', () => {
    if (resizeAnimation !== animation) return;
    resizeAnimation = null;
    header.style.removeProperty('overflow');
  }, { once: true });
}, { flush: 'pre' });

onBeforeUnmount(clearResizeAnimation);

const refreshFocusLock = () => {
  window.requestAnimationFrame(() => {
    const activeElement = document.activeElement;
    focusLocksCompactMode.value = Boolean(
      activeElement
      && headerRef.value?.contains(activeElement)
      && (
        activeElement.matches('input, select, textarea')
        || activeElement.hasAttribute('data-sticky-header-lock')
      )
    );
  });
};
const startTitleEdit = () => {
  titleDraft.value = props.title;
  editingTitle.value = true;
};

const commitTitle = () => {
  emit('update:title', titleDraft.value.trim());
  editingTitle.value = false;
};

const onWorkflowChange = async (event: Event) => {
  const select = event.target as HTMLSelectElement;
  emit('change-workflow', select.value as OrderWorkflowType);
  await nextTick();
  select.value = props.workflow;
};
</script>

<template>
  <header
    ref="headerRef"
    class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 px-3 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-950/95 sm:px-5"
    :class="effectiveCompact ? 'py-2' : 'py-3'"
    @focusin="refreshFocusLock"
    @focusout="refreshFocusLock"
  >
    <div ref="contentRef">
    <div class="flex gap-2 sm:gap-3" :class="effectiveCompact ? 'h-9 items-center' : 'items-start'">
      <div class="min-w-0 flex-1">
        <div v-if="effectiveCompact" class="flex min-w-0 items-center gap-2">
          <span class="shrink-0 text-xs font-semibold text-slate-600 dark:text-slate-300">№{{ orderId }}</span>
          <button type="button" class="min-w-0 flex-1 truncate text-left text-sm font-semibold text-slate-950 dark:text-white" title="Изменить название" @click="startTitleEdit">
            {{ title || 'Без названия' }}
          </button>
        </div>
        <template v-else>
        <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span class="font-semibold text-slate-700 dark:text-slate-200">Заказ №{{ orderId }}</span>
          <span v-if="isWebsiteOrder" class="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200">Сайт</span>
          <span class="inline-flex items-center gap-1">
            <Clock3 :size="13" aria-hidden="true" />
            {{ viewModel.stageLabel }} · {{ viewModel.stageAge }}
          </span>
        </div>

        <div v-if="editingTitle" class="mt-1.5 flex gap-2">
          <input
            v-model="titleDraft"
            class="field-input h-9 min-w-0 flex-1 font-semibold"
            maxlength="160"
            aria-label="Название заказа"
            @keydown.enter.prevent="commitTitle"
            @keydown.esc.prevent="editingTitle = false"
          />
          <button type="button" class="btn-mini-outline h-9 px-2" aria-label="Применить название" @click="commitTitle">
            <Check :size="17" />
          </button>
        </div>
        <button v-else type="button" class="mt-1 flex max-w-full items-start gap-1.5 text-left" title="Изменить название" @click="startTitleEdit">
          <span class="break-words text-base font-semibold leading-5 text-slate-950 dark:text-white sm:text-lg sm:leading-6">{{ title || 'Без названия' }}</span>
          <Pencil :size="14" class="mt-1 shrink-0 text-slate-400" aria-hidden="true" />
        </button>
        <p v-if="showCustomerName" class="mt-1 break-words text-xs leading-4 text-slate-500 dark:text-slate-400">
          {{ customerName }}
        </p>
        </template>
      </div>

      <div class="flex shrink-0 items-center gap-1">
        <button
          v-if="effectiveCompact && dirty"
          type="button"
          class="btn-mini h-9 w-9 justify-center p-0"
          :disabled="saving"
          :title="saving ? 'Сохраняем' : 'Не сохранено — сохранить'"
          :aria-label="saving ? 'Сохраняем изменения' : 'Сохранить изменения'"
          @click="emit('save')"
        >
          <Save :size="15" />
        </button>
        <div class="relative">
          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            aria-label="Дополнительные действия"
            :aria-expanded="menuOpen"
            @click="menuOpen = !menuOpen"
          >
            <MoreVertical :size="18" />
          </button>
          <div v-if="menuOpen" class="absolute right-0 top-11 z-50 w-52 rounded-lg border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800" @click="emit('hold'); menuOpen = false">
              <Play v-if="isOnHold" :size="16" />
              <Pause v-else :size="16" />
              {{ isOnHold ? 'Вернуть в работу' : 'Отложить заказ' }}
            </button>
            <div class="my-1 border-t border-slate-200 dark:border-slate-700" />
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950/30" @click="emit('delete'); menuOpen = false">
              <Trash2 :size="16" />
              Удалить заказ
            </button>
          </div>
        </div>
        <button type="button" class="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" aria-label="Закрыть карточку заказа" @click="emit('close')">
          <X :size="20" />
        </button>
      </div>
    </div>

    <div v-if="effectiveCompact" class="mt-2 flex h-8 min-w-0 items-center gap-2">
      <span
        class="inline-flex min-w-0 max-w-[42%] items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300"
        :title="viewModel.stageLabel"
      >
        <Clock3 :size="14" class="shrink-0" aria-hidden="true" />
        <span class="truncate">{{ viewModel.stageLabel }}</span>
      </span>
      <button
        type="button"
        class="btn-mini h-8 min-w-0 flex-1 justify-center gap-1.5 px-2.5 text-xs"
        :title="viewModel.nextAction.label"
        @click="emit('next')"
      >
        <span class="truncate">{{ viewModel.nextAction.label }}</span>
        <ArrowRight :size="14" class="shrink-0" aria-hidden="true" />
      </button>
    </div>

    <div v-if="!effectiveCompact" class="mt-2.5 flex flex-wrap items-center gap-2">
      <label class="relative inline-flex min-w-0 items-center">
        <span class="sr-only">Сценарий заказа</span>
        <select
          :value="workflow"
          class="h-8 max-w-[210px] appearance-none rounded-lg border border-slate-200 bg-slate-50 py-1 pl-2.5 pr-7 text-xs font-semibold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          @change="onWorkflowChange"
        >
          <option v-for="option in ORDER_WORKFLOW_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <ChevronDown :size="14" class="pointer-events-none absolute right-2 text-slate-400" />
      </label>
      <span class="rounded-lg bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">Сумма {{ formatMoney(total) }}</span>
      <span class="text-xs text-slate-500 dark:text-slate-400">оплачено {{ formatMoney(paid) }}</span>
      <span class="text-xs font-semibold" :class="balance > 0 ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'">
        {{ balance > 0 ? 'долг ' + formatMoney(balance) : 'долга нет' }}
      </span>
    </div>

    <div v-if="!effectiveCompact" class="mt-2.5 flex items-center gap-2">
      <button type="button" class="btn-mini min-w-0 flex-1 justify-center text-xs sm:flex-none" @click="emit('next')">{{ viewModel.nextAction.label }}</button>
      <button v-if="balance > 0" type="button" class="btn-mini-outline hidden h-9 text-xs sm:inline-flex" @click="emit('payments')">Внести оплату</button>
      <span v-if="!dirty" class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg bg-slate-100 px-3 text-xs font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        <Check :size="15" />
        <span class="hidden sm:inline">Сохранено</span>
      </span>
      <div v-else class="flex shrink-0 items-center gap-1.5">
        <span class="hidden text-xs font-semibold text-amber-700 dark:text-amber-200 lg:inline">Есть изменения</span>
        <button type="button" class="btn-mini-outline h-9 w-9 justify-center p-0" :disabled="saving" title="Отменить изменения" aria-label="Отменить изменения" @click="emit('discard')">
          <Undo2 :size="15" />
        </button>
        <button type="button" class="btn-mini h-9 gap-1.5 px-3 text-xs" :disabled="saving" @click="emit('save')">
          <Save :size="15" />
          <span class="hidden sm:inline">{{ saving ? 'Сохраняем' : 'Сохранить' }}</span>
        </button>
      </div>
    </div>
    </div>
  </header>
</template>
