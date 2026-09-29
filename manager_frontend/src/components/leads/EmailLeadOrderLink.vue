<script setup lang="ts">
import { ref, watch } from 'vue';
import type { EmailLeadLinkTarget } from '../../client';
import { ManagerLeadsInboxService } from '../../client';
import { confirmDialog } from '../../services/ui-feedback';

const props = defineProps<{ sourceOrderId: number; linkedOrderId?: number | null }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const expanded = ref(false);
const targetText = ref('');
const preview = ref<EmailLeadLinkTarget | null>(null);
const checking = ref(false);
const saving = ref(false);
const error = ref('');

watch(targetText, (value, _, onCleanup) => {
  preview.value = null;
  error.value = '';
  const id = Number(value);
  if (!Number.isSafeInteger(id) || id <= 0) return;
  let stale = false;
  const timer = setTimeout(async () => {
    checking.value = true;
    try {
      const target = await ManagerLeadsInboxService.previewManagerEmailLeadLinkTarget(props.sourceOrderId, id);
      if (!stale) preview.value = target;
    } catch (caught) {
      if (!stale) error.value = caught instanceof Error ? caught.message : 'Заказ не найден';
    } finally {
      if (!stale) checking.value = false;
    }
  }, 300);
  onCleanup(() => { stale = true; clearTimeout(timer); checking.value = false; });
});

const link = async () => {
  if (!preview.value || saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    await ManagerLeadsInboxService.linkManagerEmailLeadToOrder(props.sourceOrderId, {
      target_order_id: preview.value.order_id,
    });
    emit('changed');
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось привязать письмо';
  } finally {
    saving.value = false;
  }
};

const unlink = async () => {
  if (!props.linkedOrderId || saving.value) return;
  if (!await confirmDialog({
    title: 'Вернуть письмо во входящие?',
    description: `Связь с заказом #${props.linkedOrderId} будет снята. Исходное письмо и файлы останутся у обращения #${props.sourceOrderId}.`,
    confirmText: 'Снять связь',
    variant: 'warning',
  })) return;
  saving.value = true;
  error.value = '';
  try {
    await ManagerLeadsInboxService.unlinkManagerEmailLeadFromOrder(props.sourceOrderId);
    emit('changed');
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось снять связь';
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div class="mx-4 mb-3 text-xs">
    <div v-if="linkedOrderId" class="flex flex-wrap items-center gap-3">
      <a class="font-semibold text-brand-700 underline dark:text-brand-300" :href="`/manager/orders/kanban?orderId=${linkedOrderId}`">Связано с заказом #{{ linkedOrderId }}</a>
      <button type="button" class="text-slate-600 underline disabled:opacity-50 dark:text-slate-300" :disabled="saving" @click="unlink">Снять связь</button>
    </div>
    <template v-else>
      <button type="button" class="font-semibold text-brand-700 underline dark:text-brand-300" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ expanded ? 'Скрыть привязку' : 'Привязать письмо к заказу' }}
      </button>
      <div v-if="expanded" class="mt-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-900/40">
        <label class="block font-medium text-slate-700 dark:text-slate-200" :for="`email-lead-target-${sourceOrderId}`">Номер существующего заказа</label>
        <input :id="`email-lead-target-${sourceOrderId}`" v-model.trim="targetText" inputmode="numeric" pattern="[0-9]*" class="field-input mt-1 w-40" placeholder="Например, 398" />
        <p v-if="checking" class="mt-2 text-slate-500">Проверяем заказ…</p>
        <p v-if="preview" class="mt-2 text-slate-700 dark:text-slate-200">#{{ preview.order_id }} · {{ preview.customer_name || preview.title }} · {{ preview.status }}</p>
        <p v-if="error" class="mt-2 text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
        <button v-if="preview" type="button" class="mt-2 rounded-lg bg-brand-600 px-3 py-2 font-semibold text-white disabled:opacity-50" :disabled="saving" @click="link">
          {{ saving ? 'Привязываем…' : `Привязать к #${preview.order_id}` }}
        </button>
      </div>
    </template>
  </div>
</template>
