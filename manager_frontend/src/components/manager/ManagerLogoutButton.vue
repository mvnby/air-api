<script setup lang="ts">
import { ref } from 'vue';
import { Loader2, LogOut } from 'lucide-vue-next';

import { clearManagerSession, logoutManager } from '../../services/manager-session';
import { getApiErrorMessage } from '../../utils/api-errors';

defineProps<{ collapsed: boolean }>();

const emit = defineEmits<{
  loggedOut: [];
  error: [message: string];
}>();

const loading = ref(false);

const logout = async () => {
  if (loading.value) return;
  loading.value = true;
  try {
    await logoutManager();
    emit('loggedOut');
    clearManagerSession();
  } catch (error) {
    emit('error', getApiErrorMessage(error) || 'Повторите попытку');
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <div class="p-3 border-t border-gray-100">
    <button
      data-testid="manager-logout"
      class="w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-60"
      :class="collapsed ? 'md:justify-center md:px-0' : ''"
      :disabled="loading"
      :title="collapsed ? 'Выйти' : ''"
      @click="logout"
    >
      <Loader2 v-if="loading" class="h-5 w-5 shrink-0 animate-spin" />
      <LogOut v-else class="h-5 w-5 shrink-0" />
      <span :class="collapsed ? 'md:hidden' : ''">
        {{ loading ? 'Выходим...' : 'Выйти' }}
      </span>
    </button>
  </div>
</template>
