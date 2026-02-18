<script setup lang="ts">
type CustomerLike = {
  id?: number | null;
  name?: string | null;
  full_legal_name?: string | null;
  inn?: string | null;
  phone?: string | null;
  email?: string | null;
  legal_address?: string | null;
  bank_name?: string | null;
  bic?: string | null;
  iban?: string | null;
};

const props = withDefaults(defineProps<{
  customer: CustomerLike | null | undefined;
  mode?: 'compact' | 'expanded';
  showOpenButton?: boolean;
}>(), {
  mode: 'compact',
  showOpenButton: true,
});

const emit = defineEmits<{
  open: [];
}>();

const displayName = () => props.customer?.full_legal_name || props.customer?.name || '—';
</script>

<template>
  <div class="customer-card">
    <div v-if="mode === 'compact'" class="customer-compact">
      <p class="customer-compact-line">
        {{ displayName() }}
      </p>
      <p class="customer-compact-meta">
        УНП: {{ customer?.inn || '—' }} · {{ customer?.phone || '—' }} · {{ customer?.email || '—' }}
      </p>
    </div>

    <div v-else class="customer-expanded">
      <div class="grid gap-3 md:grid-cols-2">
        <div class="field">
          <span>Имя / компания</span>
          <strong>{{ displayName() }}</strong>
        </div>
        <div class="field">
          <span>УНП</span>
          <strong>{{ customer?.inn || '—' }}</strong>
        </div>
        <div class="field">
          <span>Телефон</span>
          <strong>{{ customer?.phone || '—' }}</strong>
        </div>
        <div class="field">
          <span>Email</span>
          <strong>{{ customer?.email || '—' }}</strong>
        </div>
        <div class="field md:col-span-2">
          <span>Юридический адрес</span>
          <strong>{{ customer?.legal_address || '—' }}</strong>
        </div>
        <div class="field md:col-span-2">
          <span>Банк</span>
          <strong>{{ customer?.bank_name || '—' }}</strong>
        </div>
        <div class="field">
          <span>BIC</span>
          <strong>{{ customer?.bic || '—' }}</strong>
        </div>
        <div class="field">
          <span>IBAN</span>
          <strong>{{ customer?.iban || '—' }}</strong>
        </div>
      </div>
    </div>

    <button v-if="showOpenButton" class="btn-mini-outline mt-3" :disabled="!customer?.id" @click="emit('open')">
      Открыть карточку
    </button>
  </div>
</template>

<style scoped>
.customer-card {
  border: 1px solid rgb(51 65 85 / 0.8);
  background: rgb(15 23 42 / 0.55);
  border-radius: 0.9rem;
  padding: 0.85rem;
}

.customer-compact-line {
  color: rgb(241 245 249);
  font-weight: 600;
}

.customer-compact-meta {
  margin-top: 0.25rem;
  color: rgb(148 163 184);
  font-size: 0.82rem;
  line-height: 1.35;
  word-break: break-word;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.field span {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.68rem;
  color: rgb(148 163 184);
}

.field strong {
  color: rgb(241 245 249);
  font-weight: 600;
  word-break: break-word;
}
</style>
