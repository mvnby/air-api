<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ArrowLeft, ArrowRight, Check, Clock3, MoreVertical, Pause, Pencil, Play, Save, Trash2, Undo2, X } from 'lucide-vue-next';
import OrderMoney from './OrderMoney.vue';
import MoneyText from '../money/MoneyText.vue';
import { ORDER_WORKFLOW_OPTIONS, type OrderWorkflowType, type OrderWorkspaceViewModel } from './order-workspace';
import { STICKY_HEADER_RESIZE_DURATION_MS } from '../../composables/useSmartStickyHeader';

const props = defineProps<{
  orderId?: number;
  backLabel?: string;
  title: string;
  customerName?: string;
  objectLabel?: string;
  workflow: OrderWorkflowType;
  viewModel: OrderWorkspaceViewModel;
  total: number;
  paid: number;
  balance: number;
  isWebsiteOrder?: boolean;
  isOnHold?: boolean;
  canPrintEnvelope?: boolean;
  dirty?: boolean;
  saving?: boolean;
  autosaveEnabled?: boolean;
  saveFailed?: boolean;
  saveStatusText?: string;
  compact?: boolean;
  workspace?: boolean;
  usageEnabled?: boolean;
  canViewUsageReport?: boolean;
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
  envelope: [];
  'toggle-autosave': [];
  'usage-toggle': [];
  'usage-report': [];
}>();

const editingTitle = ref(false);
const menuOpen = ref(false);
const titleDraft = ref('');
const headerRef = ref<HTMLElement | null>(null);
const contentRef = ref<HTMLElement | null>(null);
const focusLocksCompactMode = ref(false);
const effectiveCompact = computed(() => Boolean(props.workspace || (props.compact && !editingTitle.value && !menuOpen.value && !focusLocksCompactMode.value)));
const titleTriggerRef = ref<HTMLButtonElement | null>(null);
const titleInputRef = ref<HTMLInputElement | null>(null);
const menuTriggerRef = ref<HTMLButtonElement | null>(null);
const menuRef = ref<HTMLElement | null>(null);
const saveLabel = computed(() => props.saving ? 'Сохраняем' : props.saveFailed ? 'Не удалось сохранить' : props.dirty ? 'Есть изменения' : 'Сохранено');
const showCustomerName = computed(() => {
  const customerName = String(props.customerName || '').trim();
  return Boolean(customerName);
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
const startTitleEdit = async () => {
  titleDraft.value = props.title;
  editingTitle.value = true;
  await nextTick();
  titleInputRef.value?.focus();
};
const finishTitleEdit = async () => {
  editingTitle.value = false;
  await nextTick();
  titleTriggerRef.value?.focus();
};
const closeMenu = async (restoreFocus = true) => {
  menuOpen.value = false;
  if (!restoreFocus) return;
  await nextTick();
  menuTriggerRef.value?.focus();
};
const runMenuAction = async (action: () => void) => {
  await closeMenu();
  action();
};
const toggleMenu = async () => {
  if (menuOpen.value) return closeMenu();
  menuOpen.value = true;
  await nextTick();
  menuRef.value?.querySelector<HTMLElement>('button, select')?.focus();
};
const onDocumentPointerDown = (event: PointerEvent) => {
  const target = event.target as Node | null;
  if (menuOpen.value && target && !menuRef.value?.contains(target) && !menuTriggerRef.value?.contains(target)) void closeMenu(false);
};
onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown));
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointerDown));

const commitTitle = () => {
  emit('update:title', titleDraft.value.trim());
  void finishTitleEdit();
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
    <button v-if="backLabel && !workspace" type="button" class="mb-1 inline-flex min-h-9 items-center gap-1.5 text-sm font-semibold text-brand-700 dark:text-brand-200" @click="emit('close')"><ArrowLeft :size="17" />{{ backLabel }}</button>
    <div class="flex gap-2 sm:gap-3" :class="effectiveCompact ? 'min-h-9 items-center' : 'items-start'">
      <button v-if="backLabel && workspace" type="button" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-brand-700 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 dark:text-brand-200 dark:hover:bg-slate-800" :aria-label="backLabel" :title="backLabel" @click="emit('close')"><ArrowLeft :size="18" aria-hidden="true" /></button>
      <div class="min-w-0 flex-1">
        <div v-if="effectiveCompact" class="flex h-6 min-w-0 items-center gap-2">
          <span class="shrink-0 text-xs font-semibold text-slate-600 dark:text-slate-300">№{{ orderId }}</span>
          <div v-if="editingTitle" class="flex h-6 min-w-0 flex-1 items-center gap-1">
            <input ref="titleInputRef" v-model="titleDraft" class="field-input h-7 min-w-0 flex-1 py-0 text-sm font-semibold" maxlength="160" aria-label="Название заказа" @input="emit('update:title', ($event.target as HTMLInputElement).value)" @keydown.enter.prevent="commitTitle" @keydown.esc.stop.prevent="finishTitleEdit" />
            <button type="button" class="btn-mini-outline h-7 px-1" aria-label="Применить название" @click="commitTitle"><Check :size="15" aria-hidden="true" /></button>
          </div>
          <button v-else ref="titleTriggerRef" type="button" class="min-w-0 flex-1 truncate rounded text-left text-sm font-semibold leading-5 text-slate-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 dark:text-white" :title="title || 'Без названия'" :aria-label="`Изменить название: ${title || 'Без названия'}`" @click="startTitleEdit">{{ title || 'Без названия' }}</button>
        </div>
        <p v-if="effectiveCompact" class="h-5 truncate text-xs leading-5 text-slate-600 dark:text-slate-300" :title="[customerName || 'Клиент не указан', objectLabel].filter(Boolean).join(' · ')" data-order-header-customer>{{ customerName || 'Клиент не указан' }}<span v-if="objectLabel"> · {{ objectLabel }}</span></p>
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
            ref="titleInputRef"
            v-model="titleDraft"
            @input="emit('update:title', ($event.target as HTMLInputElement).value)"
            class="field-input h-9 min-w-0 flex-1 font-semibold"
            maxlength="160"
            aria-label="Название заказа"
            @keydown.enter.prevent="commitTitle"
            @keydown.esc.stop.prevent="finishTitleEdit"
          />
          <button type="button" class="btn-mini-outline h-9 px-2" aria-label="Применить название" @click="commitTitle">
            <Check :size="17" />
          </button>
        </div>
        <button v-else ref="titleTriggerRef" type="button" class="mt-1 flex max-w-full items-start gap-1.5 text-left" :title="title || 'Без названия'" :aria-label="`Изменить название: ${title || 'Без названия'}`" @click="startTitleEdit">
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
          v-if="(effectiveCompact || workspace) && (dirty || saveFailed)"
          type="button"
          class="btn-mini h-9 w-9 justify-center p-0"
          :disabled="saving"
          :title="saving ? 'Сохраняем' : saveFailed ? 'Повторить сохранение' : 'Сохранить изменения'"
          :aria-label="saving ? 'Сохраняем изменения' : saveFailed ? 'Повторить сохранение' : 'Сохранить изменения'"
          @click="emit('save')"
        >
          <Save :size="15" />
        </button>
        <button v-if="workspace && dirty" type="button" class="btn-mini-outline h-9 w-9 justify-center p-0" :disabled="saving" title="Отменить изменения" aria-label="Отменить изменения" @click="emit('discard')"><Undo2 :size="15" /></button>
        <div class="relative">
          <button
            ref="menuTriggerRef"
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            aria-label="Дополнительные действия"
            :aria-expanded="menuOpen"
            :aria-controls="`order-actions-${orderId || 'new'}`"
            @click="toggleMenu"
            @keydown.esc.stop.prevent="closeMenu()"
          >
            <MoreVertical :size="18" />
          </button>
          <div v-if="menuOpen" :id="`order-actions-${orderId || 'new'}`" ref="menuRef" aria-label="Действия с заказом" @keydown.esc.stop.prevent="closeMenu()" class="absolute right-0 top-11 z-50 w-56 rounded-lg border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <button v-if="canPrintEnvelope" type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800" @click="runMenuAction(() => emit('envelope'))">Печать конверта</button>
            <label class="block px-3 py-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
              Сценарий заказа
              <select :value="workflow" class="field-input mt-1.5 h-8 w-full text-xs" data-order-usage="workflow-change" @change="onWorkflowChange">
                <option v-for="option in ORDER_WORKFLOW_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
            <div class="my-1 border-t border-slate-200 dark:border-slate-700" />
            <button v-if="usageEnabled !== undefined" type="button" class="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800" data-order-usage="usage-toggle" @click="emit('usage-toggle')">
              Сбор статистики
              <span class="text-xs text-slate-500">{{ usageEnabled ? 'вкл.' : 'выкл.' }}</span>
            </button>
            <button v-if="canViewUsageReport" type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800" data-order-usage="usage-report" @click="runMenuAction(() => emit('usage-report'))">
              Отчёт по использованию
            </button>
            <div v-if="usageEnabled !== undefined || canViewUsageReport" class="my-1 border-t border-slate-200 dark:border-slate-700" />
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800" @click="runMenuAction(() => emit('hold'))">
              <Play v-if="isOnHold" :size="16" />
              <Pause v-else :size="16" />
              {{ isOnHold ? 'Вернуть в работу' : 'Отложить заказ' }}
            </button>
            <div class="my-1 border-t border-slate-200 dark:border-slate-700" />
            <button type="button" class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950/30" @click="runMenuAction(() => emit('delete'))">
              <Trash2 :size="16" />
              Удалить заказ
            </button>
          </div>
        </div>
        <button v-if="!backLabel" type="button" class="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" aria-label="Закрыть карточку заказа" @click="emit('close')">
          <X :size="20" />
        </button>
      </div>
    </div>

    <div class="mt-1 flex min-h-8 items-center gap-x-3 text-xs" :class="workspace ? 'flex-nowrap' : 'flex-wrap gap-y-1'">
      <button
        type="button"
        role="switch"
        :aria-checked="Boolean(autosaveEnabled)"
        aria-label="Автосохранение заказа"
        :title="`Автосохранение ${autosaveEnabled ? 'вкл.' : 'выкл.'}`"
        data-order-usage="autosave-toggle"
        class="inline-flex min-h-8 items-center gap-2 font-medium text-slate-700 dark:text-slate-200"
        @click="emit('toggle-autosave')"
      >
        <span class="relative h-4 w-7 rounded-full" :class="autosaveEnabled ? 'bg-brand-600' : 'bg-slate-400'" aria-hidden="true">
          <span class="absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform" :class="autosaveEnabled ? 'left-0.5 translate-x-3' : 'left-0.5'" />
        </span>
        <span :class="workspace ? 'hidden sm:inline' : ''">Автосохранение {{ autosaveEnabled ? 'вкл.' : 'выкл.' }}</span>
      </button>
      <span role="status" aria-live="polite" class="w-36 shrink-0" :title="saveStatusText" :class="saveFailed && !saving ? 'text-red-700 dark:text-red-300' : 'text-slate-500 dark:text-slate-400'">{{ saveLabel }}</span>
      <span v-if="workspace" class="min-w-0 truncate rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300" :title="viewModel.stageLabel">{{ viewModel.stageLabel }}</span>
    </div>

    <div v-if="effectiveCompact && !workspace" class="mt-2 flex h-8 min-w-0 items-center gap-2">
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
        <span class="truncate"><MoneyText :text="viewModel.nextAction.label" /></span>
        <ArrowRight :size="14" class="shrink-0" aria-hidden="true" />
      </button>
    </div>

    <div v-if="!effectiveCompact && !workspace" class="mt-2.5 flex flex-wrap items-center gap-2">
      <span class="rounded-lg bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">Сумма <OrderMoney class="relative" :value="total" /></span>
      <span class="text-xs text-slate-500 dark:text-slate-400">оплачено <OrderMoney class="relative" :value="paid" /></span>
      <span class="text-xs font-semibold" :class="balance > 0 ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-700 dark:text-emerald-300'">
        <template v-if="balance > 0">долг <OrderMoney class="relative" :value="balance" /></template><template v-else>долга нет</template>
      </span>
    </div>

    <div v-if="!effectiveCompact && !workspace" class="mt-2.5 flex items-center gap-2">
      <button type="button" class="btn-mini min-w-0 flex-1 justify-center text-xs sm:flex-none" @click="emit('next')"><MoneyText :text="viewModel.nextAction.label" /></button>
      <button v-if="balance > 0" type="button" class="btn-mini-outline hidden h-9 text-xs sm:inline-flex" @click="emit('payments')">Внести оплату</button>
      <div v-if="dirty" class="flex shrink-0 items-center gap-1.5">
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
