<script setup lang="ts">
import { computed, ref } from 'vue';
import { AlertTriangle, CircleCheck, CircleX, Info, Loader2, X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';
import {
  cancelActiveDialog,
  dismissNotification,
  setDialogInput,
  submitActiveDialog,
  uiDialogState,
  uiNotifications,
} from '../../services/ui-feedback';

const dialogRef = ref<HTMLElement | null>(null);
const confirmButtonRef = ref<HTMLButtonElement | null>(null);
const inputRef = ref<HTMLInputElement | HTMLTextAreaElement | null>(null);
const isOpen = computed(() => uiDialogState.open);
const initialFocusRef = computed<HTMLElement | null>(() => inputRef.value || confirmButtonRef.value);

const tone = computed(() => ({
  default: {
    icon: Info,
    iconClass: 'bg-teal-50 text-teal-700 dark:bg-teal-950/60 dark:text-teal-300',
    buttonClass: 'bg-teal-600 text-white hover:bg-teal-700 focus-visible:ring-teal-500',
  },
  warning: {
    icon: AlertTriangle,
    iconClass: 'bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
    buttonClass: 'bg-amber-500 text-white hover:bg-amber-600 focus-visible:ring-amber-500',
  },
  danger: {
    icon: CircleX,
    iconClass: 'bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300',
    buttonClass: 'bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500',
  },
}[uiDialogState.variant]));

const close = () => cancelActiveDialog();
const onBackdrop = () => {
  if (!uiDialogState.loading) close();
};

useDialogA11y({ open: isOpen, dialogRef, initialFocusRef, close });
</script>

<template>
  <Teleport to="body">
    <Transition name="ui-dialog-fade">
      <div
        v-if="uiDialogState.open"
        class="fixed inset-0 z-[250] flex items-end justify-center bg-slate-950/55 p-0 backdrop-blur-[2px] sm:items-center sm:p-4"
        @mousedown.self="onBackdrop"
      >
        <section
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ui-dialog-title"
          :aria-describedby="uiDialogState.description ? 'ui-dialog-description' : undefined"
          tabindex="-1"
          class="w-full max-w-md rounded-t-lg border border-slate-200 bg-white shadow-2xl outline-none dark:border-slate-700 dark:bg-slate-900 sm:rounded-lg"
        >
          <header class="flex items-start gap-3 border-b border-slate-100 px-4 py-4 dark:border-slate-800 sm:px-5">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg" :class="tone.iconClass">
              <component :is="tone.icon" class="h-5 w-5" aria-hidden="true" />
            </span>
            <div class="min-w-0 flex-1">
              <h2 id="ui-dialog-title" class="text-base font-semibold text-slate-950 dark:text-white">
                {{ uiDialogState.title }}
              </h2>
              <p
                v-if="uiDialogState.description"
                id="ui-dialog-description"
                class="mt-1 whitespace-pre-line text-sm leading-5 text-slate-600 dark:text-slate-300"
              >
                {{ uiDialogState.description }}
              </p>
            </div>
            <button
              type="button"
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800"
              aria-label="Закрыть"
              :disabled="uiDialogState.loading"
              @click="close"
            >
              <X class="h-5 w-5" />
            </button>
          </header>

          <div v-if="uiDialogState.kind === 'prompt'" class="px-4 pt-4 sm:px-5">
            <label class="block text-sm font-medium text-slate-700 dark:text-slate-200">
              <span v-if="uiDialogState.inputLabel" class="mb-1.5 block">{{ uiDialogState.inputLabel }}</span>
              <textarea
                v-if="uiDialogState.inputKind === 'textarea'"
                ref="inputRef"
                rows="4"
                class="field-input min-h-24 w-full resize-y"
                :value="uiDialogState.inputValue"
                :placeholder="uiDialogState.placeholder"
                :disabled="uiDialogState.loading"
                @input="setDialogInput(($event.target as HTMLTextAreaElement).value)"
                @keydown.ctrl.enter.prevent="submitActiveDialog"
                @keydown.meta.enter.prevent="submitActiveDialog"
              />
              <input
                v-else
                ref="inputRef"
                class="field-input w-full"
                :value="uiDialogState.inputValue"
                :placeholder="uiDialogState.placeholder"
                :disabled="uiDialogState.loading"
                @input="setDialogInput(($event.target as HTMLInputElement).value)"
                @keydown.enter.prevent="submitActiveDialog"
              >
            </label>
          </div>

          <p
            v-if="uiDialogState.error"
            role="alert"
            class="mx-4 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200 sm:mx-5"
          >
            {{ uiDialogState.error }}
          </p>

          <footer class="flex flex-col-reverse gap-2 px-4 py-4 sm:flex-row sm:justify-end sm:px-5">
            <button
              v-if="uiDialogState.kind !== 'message'"
              type="button"
              class="h-10 rounded-lg border border-slate-300 px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
              :disabled="uiDialogState.loading"
              @click="close"
            >
              {{ uiDialogState.cancelText }}
            </button>
            <button
              ref="confirmButtonRef"
              type="button"
              class="inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60 dark:focus-visible:ring-offset-slate-900"
              :class="tone.buttonClass"
              :disabled="uiDialogState.loading"
              @click="submitActiveDialog"
            >
              <Loader2 v-if="uiDialogState.loading" class="h-4 w-4 animate-spin" />
              {{ uiDialogState.confirmText }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>

    <div class="pointer-events-none fixed right-3 top-3 z-[260] flex w-[calc(100%-1.5rem)] max-w-sm flex-col gap-2 sm:right-5 sm:top-5">
      <TransitionGroup name="ui-toast">
        <button
          v-for="item in uiNotifications"
          :key="item.id"
          type="button"
          class="pointer-events-auto flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-sm font-medium shadow-xl"
          :class="{
            'border-emerald-500 bg-emerald-600 text-white': item.variant === 'success',
            'border-red-500 bg-red-600 text-white': item.variant === 'error',
            'border-slate-700 bg-slate-900 text-white dark:border-slate-200 dark:bg-white dark:text-slate-950': item.variant === 'info',
          }"
          :aria-label="`${item.message}. Закрыть уведомление`"
          @click="dismissNotification(item.id)"
        >
          <CircleCheck v-if="item.variant === 'success'" class="mt-0.5 h-4 w-4 shrink-0" />
          <CircleX v-else-if="item.variant === 'error'" class="mt-0.5 h-4 w-4 shrink-0" />
          <Info v-else class="mt-0.5 h-4 w-4 shrink-0" />
          <span class="min-w-0 flex-1">{{ item.message }}</span>
          <X class="mt-0.5 h-4 w-4 shrink-0 opacity-75" />
        </button>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.ui-dialog-fade-enter-active,
.ui-dialog-fade-leave-active {
  transition: opacity 160ms ease;
}
.ui-dialog-fade-enter-active section,
.ui-dialog-fade-leave-active section {
  transition: transform 160ms ease, opacity 160ms ease;
}
.ui-dialog-fade-enter-from,
.ui-dialog-fade-leave-to {
  opacity: 0;
}
.ui-dialog-fade-enter-from section,
.ui-dialog-fade-leave-to section {
  opacity: 0;
  transform: translateY(8px) scale(0.99);
}
.ui-toast-enter-active,
.ui-toast-leave-active {
  transition: opacity 160ms ease, transform 160ms ease;
}
.ui-toast-enter-from,
.ui-toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
