<script setup lang="ts">
import { computed, ref } from 'vue';
import { Archive, Check, Copy, MoreHorizontal, Pencil, Plus, RotateCcw, Send, ThumbsDown, ThumbsUp } from 'lucide-vue-next';
import type { OrderProposalResponse } from '../../client';
import {
  PROPOSAL_STATUS_META,
  normalizeProposalStatus,
  proposalPrimaryAction,
  proposalPrimaryActionLabel,
} from './proposal-lifecycle';
import { formatMoney } from './order-utils';

const props = defineProps<{
  proposals: OrderProposalResponse[];
  activeProposalId?: number | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  open: [proposal: OrderProposalResponse];
  select: [proposal: OrderProposalResponse];
  create: [];
  duplicate: [];
  rename: [];
  archive: [];
  'change-status': [status: 'draft' | 'ready_to_send' | 'sent' | 'approved' | 'rejected'];
  send: [];
}>();

const menuOpen = ref(false);
const responseOpen = ref(false);
const activeProposal = computed(() => (
  props.proposals.find((proposal) => proposal.id === props.activeProposalId)
  || props.proposals.find((proposal) => proposal.is_selected)
  || props.proposals[0]
  || null
));
const lineCount = (proposal: OrderProposalResponse) => (proposal.product_lines?.length || 0) + (proposal.service_lines?.length || 0);
const activeStatus = computed(() => normalizeProposalStatus(activeProposal.value?.status));
const activeLineCount = computed(() => activeProposal.value ? lineCount(activeProposal.value) : 0);
const activeCanFinish = computed(() => activeLineCount.value > 0 && Number(activeProposal.value?.total_amount || 0) > 0);
const primaryAction = computed(() => proposalPrimaryAction(activeStatus.value));
const primaryLabel = computed(() => (
  activeStatus.value === 'draft' && !activeCanFinish.value
    ? 'Заполните предложение'
    : proposalPrimaryActionLabel(activeStatus.value)
));

const statusMeta = (proposal: OrderProposalResponse) => PROPOSAL_STATUS_META[normalizeProposalStatus(proposal.status)];
const lineLabel = (proposal: OrderProposalResponse) => {
  const count = lineCount(proposal);
  const mod100 = count % 100;
  const mod10 = count % 10;
  const noun = mod100 >= 11 && mod100 <= 14 ? 'позиций' : mod10 === 1 ? 'позиция' : mod10 >= 2 && mod10 <= 4 ? 'позиции' : 'позиций';
  return `${count} ${noun}`;
};
const toneClass = (proposal: OrderProposalResponse) => ({
  slate: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  sky: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
  emerald: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200',
  rose: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200',
}[statusMeta(proposal).tone]);

const runPrimary = () => {
  if (!activeProposal.value || props.loading) return;
  if (!activeProposal.value.is_selected) {
    emit('select', activeProposal.value);
    return;
  }
  if (primaryAction.value === 'finish' && activeCanFinish.value) emit('change-status', 'ready_to_send');
  else if (primaryAction.value === 'send') emit('send');
  else if (primaryAction.value === 'record_response') responseOpen.value = !responseOpen.value;
  else if (primaryAction.value === 'create_variant') emit('duplicate');
};

const changeResponse = (status: 'approved' | 'rejected') => {
  responseOpen.value = false;
  emit('change-status', status);
};

defineExpose({
  openResponse: () => { responseOpen.value = true; },
});
</script>

<template>
  <div class="border-b border-slate-200 pb-3 dark:border-slate-700" @keydown.esc="menuOpen = false; responseOpen = false">
    <div v-if="proposals.length > 1" class="flex gap-2 overflow-x-auto pb-1">
      <button
        v-for="proposal in proposals"
        :key="proposal.id"
        type="button"
        class="min-w-[9.5rem] shrink-0 rounded-xl border px-3 py-2 text-left text-xs transition disabled:cursor-not-allowed disabled:opacity-60"
        :class="proposal.id === activeProposal?.id
          ? 'border-teal-500 bg-teal-50 text-teal-950 shadow-sm dark:border-teal-400 dark:bg-teal-500/10 dark:text-teal-100'
          : 'border-slate-200 bg-white text-slate-600 hover:border-teal-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'"
        :disabled="loading"
        @click="emit('open', proposal)"
      >
        <span class="flex min-w-0 items-center gap-1 font-semibold">
          <span class="truncate">{{ proposal.name }}</span>
          <Check v-if="proposal.is_selected" :size="13" class="shrink-0 text-teal-600" aria-label="Активное предложение" />
        </span>
        <span class="mt-1 flex items-center gap-1.5">
          <span class="rounded-full px-1.5 py-0.5 text-[10px] font-semibold" :class="toneClass(proposal)">{{ statusMeta(proposal).label }}</span>
          <span class="whitespace-nowrap opacity-70">{{ formatMoney(proposal.total_amount || 0) }}</span>
        </span>
      </button>
    </div>

    <div v-if="activeProposal" class="mt-2 flex min-w-0 items-center gap-2">
      <div class="min-w-0 flex-1">
        <div class="flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
          <span class="truncate font-semibold text-slate-900 dark:text-white">{{ activeProposal.name }}</span>
          <span v-if="activeProposal.is_selected" class="rounded-full bg-teal-50 px-2 py-0.5 font-semibold text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">Активное</span>
          <span class="rounded-full px-2 py-0.5 font-semibold" :class="toneClass(activeProposal)">{{ statusMeta(activeProposal).label }}</span>
        </div>
        <p class="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{{ lineLabel(activeProposal) }} · {{ formatMoney(activeProposal.total_amount || 0) }}</p>
      </div>

      <button
        v-if="!activeProposal.is_selected || primaryAction"
        type="button"
        class="btn-mini h-9 shrink-0 gap-1.5 px-3 text-xs"
        :disabled="loading"
        @click="runPrimary"
      >
        <Check v-if="!activeProposal.is_selected || primaryAction === 'finish'" :size="15" />
        <Send v-else-if="primaryAction === 'send'" :size="15" />
        <Plus v-else-if="primaryAction === 'create_variant'" :size="15" />
        <span>{{ !activeProposal.is_selected ? 'Сделать активным' : primaryLabel }}</span>
      </button>

      <div class="relative shrink-0">
        <button type="button" class="btn-mini-outline h-9 w-9 justify-center p-0" :disabled="loading" aria-label="Действия с предложением" :aria-expanded="menuOpen" @click="menuOpen = !menuOpen">
          <MoreHorizontal :size="17" />
        </button>
        <div v-if="menuOpen" class="absolute right-0 top-11 z-30 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
          <button type="button" class="menu-action" @click="emit('rename'); menuOpen = false"><Pencil :size="15" />Переименовать</button>
          <button type="button" class="menu-action" @click="emit('duplicate'); menuOpen = false"><Copy :size="15" />Создать копию</button>
          <button type="button" class="menu-action" @click="emit('create'); menuOpen = false"><Plus :size="15" />Альтернативный вариант</button>
          <button v-if="activeStatus === 'ready_to_send'" type="button" class="menu-action" @click="emit('change-status', 'sent'); menuOpen = false"><Send :size="15" />Отметить отправленным</button>
          <button v-if="activeStatus !== 'draft'" type="button" class="menu-action" @click="emit('change-status', 'draft'); menuOpen = false"><RotateCcw :size="15" />Вернуть в черновик</button>
          <button v-if="proposals.length > 1" type="button" class="menu-action danger" @click="emit('archive'); menuOpen = false"><Archive :size="15" />Перенести в архив</button>
        </div>
      </div>
    </div>

    <div v-if="responseOpen" class="mt-2 flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 p-2 dark:border-amber-500/30 dark:bg-amber-500/10">
      <span class="mr-auto text-xs font-medium text-amber-900 dark:text-amber-100">Как ответил клиент?</span>
      <button type="button" class="btn-mini h-8 gap-1.5 px-2.5 text-xs" :disabled="loading" @click="changeResponse('approved')"><ThumbsUp :size="14" />Принято</button>
      <button type="button" class="btn-mini-outline h-8 gap-1.5 px-2.5 text-xs text-rose-700" :disabled="loading" @click="changeResponse('rejected')"><ThumbsDown :size="14" />Отклонено</button>
    </div>

    <button v-if="!proposals.length" type="button" class="btn-mini w-full justify-center" :disabled="loading" @click="emit('create')"><Plus :size="16" />Создать предложение</button>
  </div>
</template>

<style scoped>
.menu-action {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 0.5rem;
  border-radius: 0.5rem;
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-size: 0.8125rem;
  color: rgb(51 65 85);
}
.menu-action:hover { background: rgb(241 245 249); }
.menu-action.danger { color: rgb(190 18 60); }
:global(.dark) .menu-action { color: rgb(226 232 240); }
:global(.dark) .menu-action.danger { color: rgb(253 164 175); }
:global(.dark) .menu-action:hover { background: rgb(30 41 59); }
</style>
