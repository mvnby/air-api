<script setup lang="ts">
import { computed, ref } from 'vue';
import type { LeadsInboxItemResponse } from '../../api';

const props = defineProps<{
  item: LeadsInboxItemResponse;
  isArchive?: boolean;
}>();

const emit = defineEmits<{
  (e: 'qualify', item: LeadsInboxItemResponse): void;
  (e: 'reject', item: LeadsInboxItemResponse): void;
  (e: 'no-answer', item: LeadsInboxItemResponse): void;
}>();

const isCommentExpanded = ref(false);

const sourceLabel: Record<string, string> = {
  site: 'Сайт',
  phone: 'Телефон',
  bot: 'Бот',
  email: 'Email',
  manager: 'Менеджер',
  other: 'Другое',
};

const sourceIcon: Record<string, string> = {
  site: 'language',
  phone: 'call',
  bot: 'smart_toy',
  email: 'email',
  manager: 'person',
  other: 'help_outline',
};

const ORDER_STATUS_MAP: Record<string, string> = {
  new_lead: 'Лид',
  negotiation: 'Переговоры',
  execution: 'Монтаж',
  closed: 'Закрыт',
};

const getSourceIcon = (source: string | null | undefined) =>
  sourceIcon[source ?? ''] ?? 'help_outline';

const getSourceLabel = (source: string | null | undefined) =>
  sourceLabel[source ?? ''] ?? source ?? '—';

const getStatusLabel = (status: string) =>
  ORDER_STATUS_MAP[status] ?? status;

const formatDate = (dt: string) => {
  const d = new Date(dt);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

const formatPhone = (phone: string | null | undefined): string => {
  if (!phone) return '';
  // Normalize to digits only
  const digits = phone.replace(/\D/g, '');
  // Expect 375XXXXXXXXX (12 digits)
  if (digits.length === 12 && digits.startsWith('375')) {
    const cc = digits.slice(0, 3);   // 375
    const op = digits.slice(3, 5);   // operator code (2 digits)
    const p1 = digits.slice(5, 8);   // 3 digits
    const p2 = digits.slice(8, 10);  // 2 digits
    const p3 = digits.slice(10, 12); // 2 digits
    return `+${cc} (${op}) ${p1}-${p2}-${p3}`;
  }
  return phone;
};

const formatEmail = (email: string | null | undefined): string => {
  return (email || '').trim();
};

const getRelativeTime = (dt: string | null | undefined) => {
  if (!dt) return '';
  const date = new Date(dt);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  
  const rtf = new Intl.RelativeTimeFormat('ru', { numeric: 'auto' });

  if (diffInSeconds < 60) {
    return rtf.format(-diffInSeconds, 'second');
  }
  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) {
    return rtf.format(-diffInMinutes, 'minute');
  }
  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) {
    return rtf.format(-diffInHours, 'hour');
  }
  const diffInDays = Math.floor(diffInHours / 24);
  return rtf.format(-diffInDays, 'day');
};

const hasLongComment = computed(() => (props.item.comment || '').length > 140);
</script>

<template>
  <div
    class="group relative bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700/60 shadow-sm hover:shadow-md transition-all duration-200"
    :class="{
      'border-l-4 border-l-teal-500': item.is_new,
      'bg-teal-50/40 dark:bg-teal-900/10': item.is_new,
    }"
  >
    <!-- Header row -->
    <div class="flex items-start justify-between gap-3 p-4 pb-2">
      <div class="flex items-center gap-2 min-w-0">
        <!-- Source icon -->
        <span
          class="material-icons-round text-[18px] shrink-0"
          :class="item.is_new ? 'text-teal-500' : 'text-slate-400 dark:text-slate-500'"
        >{{ getSourceIcon(item.source) }}</span>

        <!-- Name -->
        <div class="flex flex-col min-w-0">
          <span class="font-semibold text-slate-800 dark:text-white truncate text-sm">
            {{ item.customer_name || item.customer_full_legal_name || '(Имя не указано)' }}
          </span>
          <span v-if="item.customer_type === 'company' && item.customer_inn" class="text-[10px] text-slate-400 dark:text-slate-500 uppercase font-bold tracking-tighter">
            УНП {{ item.customer_inn }}
          </span>
        </div>
      </div>

      <!-- Badges -->
      <div class="flex items-center gap-2 shrink-0">
        <span
          v-if="item.customer_type === 'company'"
          class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-600"
        >🏢 ЮР</span>
        <span
          v-if="item.is_new"
          class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold bg-teal-500 text-white"
        >🔥 НОВЫЙ</span>
        <span
          v-else
          class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
        >{{ getStatusLabel(item.status) }}</span>
      </div>
    </div>

    <!-- Phone & source row -->
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pb-2">
      <a
        v-if="item.phone"
        :href="`tel:${item.phone}`"
        class="flex items-center gap-1 text-sm text-teal-600 dark:text-teal-400 hover:underline font-medium"
      >
        <span class="material-icons-round text-[15px]">call</span>
        {{ formatPhone(item.phone) }}
      </a>
      <a
        v-if="formatEmail(item.email)"
        :href="`mailto:${formatEmail(item.email)}`"
        class="flex min-w-0 items-center gap-1 text-sm text-teal-600 dark:text-teal-400 hover:underline font-medium"
        :title="formatEmail(item.email)"
      >
        <span class="material-icons-round text-[15px]">email</span>
        <span class="min-w-0 break-all">{{ formatEmail(item.email) }}</span>
      </a>
      <span class="text-xs text-slate-400 dark:text-slate-500 flex items-center gap-1">
        <span class="material-icons-round text-[13px]">{{ getSourceIcon(item.source) }}</span>
        {{ getSourceLabel(item.source) }}
      </span>
      <span class="text-xs text-slate-400 dark:text-slate-500 ml-auto">
        {{ formatDate(item.created_at) }}
      </span>
    </div>

    <!-- Comment (the core decision-making field) -->
    <div
      v-if="item.comment"
      class="mx-4 mb-3 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 border border-slate-100 dark:border-slate-700"
    >
      <p
        class="whitespace-pre-line text-sm text-slate-700 dark:text-slate-200 leading-relaxed"
        :class="{ 'line-clamp-3': !isCommentExpanded }"
      >
        {{ item.comment }}
      </p>
      <button
        v-if="hasLongComment"
        type="button"
        class="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-teal-700 hover:text-teal-800 dark:text-teal-300 dark:hover:text-teal-200"
        @click="isCommentExpanded = !isCommentExpanded"
      >
        <span class="material-icons-round text-[15px]">{{ isCommentExpanded ? 'expand_less' : 'expand_more' }}</span>
        {{ isCommentExpanded ? 'Свернуть' : 'Показать полностью' }}
      </button>
    </div>
    <div
      v-else
      class="mx-4 mb-3 px-3 py-2 text-sm text-slate-400 dark:text-slate-500 italic"
    >
      Комментарий отсутствует
    </div>

    <!-- No Answer Badge -->
    <div v-if="item.no_answer_at" class="mx-4 mb-4 flex items-center gap-1.5 w-fit rounded-full px-3 py-1 bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 text-[11px] font-bold tracking-wide">
      <span class="material-icons-round text-[14px]">phone_missed</span>
      Недозвон: {{ getRelativeTime(item.no_answer_at) }}
    </div>

    <!-- Actions footer -->
    <div v-if="!isArchive" class="flex flex-wrap gap-2 px-4 pb-4">
      <button
        class="flex-1 min-w-[120px] inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs md:text-sm font-semibold bg-teal-600 text-white hover:bg-teal-700 active:scale-95 transition-all"
        title="Квалифицировать (в сделку)"
        @click="emit('qualify', item)"
      >
        <span class="material-icons-round text-[16px]">check_circle</span>
        Квалифицировать
      </button>

      <button
        class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs md:text-sm font-semibold bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-900/50 active:scale-95 transition-all"
        title="Недозвон (оставить в работе)"
        @click="emit('no-answer', item)"
      >
        <span class="material-icons-round text-[16px]">timer</span>
        Недозвон
      </button>

      <button
        class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs md:text-sm font-semibold bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 active:scale-95 transition-all"
        title="Отмена / В архив"
        @click="emit('reject', item)"
      >
        <span class="material-icons-round text-[16px]">cancel</span>
        Отказ
      </button>
    </div>
  </div>
</template>
