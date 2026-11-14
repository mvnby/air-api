<script setup lang="ts">
import { inject, ref } from 'vue';
import { runGuardedUnload } from '../../services/unsaved-navigation-guard';
import { managerModuleReloadKey, recordModuleFailure, type ManagerModule, type ModuleCategory } from '../../services/manager-module-recovery';

defineOptions({ inheritAttrs: false });
const props = withDefaults(defineProps<{ loading?: boolean; module?: ManagerModule; category?: ModuleCategory }>(), {
  loading: false, module: 'unknown', category: 'route',
});
const reloadPage = inject(managerModuleReloadKey, () => window.location.reload());
const pending = ref(false);
const message = ref('');
const reload = async () => {
  if (pending.value) return;
  pending.value = true;
  message.value = '';
  try {
    const accepted = await runGuardedUnload(() => {
      recordModuleFailure(props.module, props.category, 'reload-requested');
      reloadPage();
    });
    if (!accepted) {
      recordModuleFailure(props.module, props.category, 'reload-blocked');
      message.value = 'Обновление отменено. Сохраните изменения и попробуйте снова.';
      pending.value = false;
    }
  } catch {
    recordModuleFailure(props.module, props.category, 'reload-failed');
    message.value = 'Не удалось обновить страницу. Сохраните изменения и попробуйте снова.';
    pending.value = false;
  }
};
</script>

<template>
  <section class="m-4 rounded-xl border border-[var(--kitlane-border)] bg-[var(--kitlane-surface)] p-5 text-[var(--kitlane-text)]" :role="loading ? 'status' : 'alert'" :aria-busy="loading">
    <p v-if="loading" class="font-medium">Загружаем раздел…</p>
    <template v-else>
      <h2 class="font-semibold">Не удалось загрузить раздел</h2>
      <p class="mt-2 text-sm">Возможно, приложение обновилось или пропала связь. Проверьте подключение и обновите страницу.</p>
      <p class="mt-2 text-sm">Перед обновлением сохраните изменения. Можно продолжить работу в других разделах через меню.</p>
      <button type="button" class="btn-mini mt-4 min-h-10 focus-visible:ring-2 focus-visible:ring-brand-500" :disabled="pending" @click="reload">{{ pending ? 'Обновляем…' : 'Обновить страницу' }}</button>
      <p v-if="message" class="mt-2 text-sm" role="status">{{ message }}</p>
    </template>
  </section>
</template>
