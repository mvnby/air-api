<script setup>
import { useStore } from '@nanostores/vue';
import { toastStore, removeToast } from '../../store/toast';

const toasts = useStore(toastStore);
</script>

<template>
  <div class="toast-container">
    <TransitionGroup name="toast">
      <div 
        v-for="toast in toasts" 
        :key="toast.id" 
        class="toast-item"
        :class="toast.type"
        @click="removeToast(toast.id)"
      >
        <div class="toast-icon">
            <span v-if="toast.type === 'success'" class="material-icons-round">check_circle</span>
            <span v-else-if="toast.type === 'error'" class="material-icons-round">error</span>
            <span v-else class="material-icons-round">info</span>
        </div>
        <div class="toast-message">{{ toast.message }}</div>
        <button class="toast-close">
            <span class="material-icons-round">close</span>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 100px; /* Below header */
  right: 2rem;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  pointer-events: none; /* Let clicks pass through container */
}

.toast-item {
  pointer-events: auto; /* Enable clicks on toasts */
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e8f0);
  padding: 1rem 1.25rem;
  border-radius: 1rem;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 300px;
  max-width: 400px;
  cursor: pointer;
  backdrop-filter: blur(8px);
  /* Dark mode support via vars */
  color: var(--text, #0f172a);
}

.toast-icon {
    display: flex;
    align-items: center;
    justify-content: center;
}
.toast-icon .material-icons-round {
    font-size: 1.5rem;
}

.toast-message {
    font-weight: 500;
    font-size: 0.95rem;
    flex: 1;
    line-height: 1.4;
}

.toast-close {
    background: transparent;
    border: none;
    color: var(--text-muted, #94a3b8);
    cursor: pointer;
    display: flex;
    align-items: center;
    padding: 0;
}
.toast-close:hover {
    color: var(--text, #0f172a);
}

/* Types */
.toast-item.success .toast-icon { color: #10b981; }
.toast-item.error .toast-icon { color: #ef4444; }
.toast-item.info .toast-icon { color: #3b82f6; }

/* Animation */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.4s cubic-bezier(0.5, 0, 0.15, 1);
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%) scale(0.9);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.9);
}

@media (max-width: 640px) {
    .toast-container {
        right: 1rem;
        left: 1rem;
        top: auto;
        bottom: 2rem;
    }
    .toast-item {
        width: 100%;
        max-width: none;
    }
}
</style>
