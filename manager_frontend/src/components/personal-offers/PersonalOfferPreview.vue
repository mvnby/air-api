<script setup lang="ts">
import { formatOfferDate, formatOfferMoney, type PersonalOfferPreview } from '../../services/personal-offers';
import { productReaderUrl } from '../../services/product-reader-api';

defineProps<{ offer: PersonalOfferPreview }>();

const wifiName = { builtin: 'Встроенный', ready: 'Опционально', none: 'Нет' };
</script>

<template>
  <section class="space-y-4 rounded-xl border border-[var(--mv-border)] p-4" aria-labelledby="offer-preview-heading">
    <div>
      <h2 id="offer-preview-heading" class="text-lg font-bold">Клиентский предпросмотр</h2>
      <p class="text-sm text-[var(--mv-text-muted)]">Действует до {{ formatOfferDate(offer.expires_at) }}</p>
    </div>
    <section v-for="(room, index) in offer.rooms" :key="index" class="space-y-2">
      <h3 class="break-words text-base font-semibold">{{ room.title }}</h3>
      <p v-if="room.selection_mode === 'package'" class="text-sm">В комплект входят все модели</p>
      <p v-else-if="room.options.length > 1" class="text-sm">Выберите одну модель</p>
      <p v-if="room.equipment_total_byn != null" class="text-sm font-semibold">
        {{ room.installation.mode === 'none' ? 'Итого за комплект' : 'Итого за оборудование' }}: {{ formatOfferMoney(room.equipment_total_byn) }}
      </p>
      <p v-if="room.total_with_installation_byn != null" class="text-sm font-semibold">Итого с монтажом: {{ formatOfferMoney(room.total_with_installation_byn) }}</p>
      <p v-if="room.installation.mode === 'unknown'" class="text-sm">Монтаж: стоимость уточним</p>
      <p v-if="room.installation.mode === 'fixed' && room.installation.price_byn !== null" class="text-sm">Монтаж: {{ formatOfferMoney(room.installation.price_byn) }}</p>
      <p v-if="room.installation.description" class="break-words text-sm">{{ room.installation.description }}</p>
      <ul class="grid gap-2 md:grid-cols-2">
        <li v-for="(option, position) in room.options" :key="position" class="flex min-w-0 gap-3 rounded-lg border border-[var(--mv-border)] p-3">
          <img v-if="productReaderUrl(option.main_image)" :src="productReaderUrl(option.main_image) ?? undefined" alt="" class="h-16 w-16 shrink-0 rounded object-contain" />
          <div class="min-w-0 space-y-1 break-words text-sm">
            <p class="font-semibold">{{ option.title }}</p>
            <p><s v-if="option.original_price_byn" class="mr-2 text-[var(--mv-text-muted)]">{{ formatOfferMoney(option.original_price_byn) }}</s>{{ formatOfferMoney(option.price_byn) }}</p>
            <p v-if="option.total_price_byn" class="font-semibold">С монтажом: {{ formatOfferMoney(option.total_price_byn) }}</p>
            <dl class="grid grid-cols-[auto_1fr] gap-x-2 text-xs">
              <dt>Охлаждение</dt><dd>{{ option.cooling_power_kw == null ? 'Нет данных' : option.cooling_power_kw + ' кВт' }}</dd>
              <dt>Шум</dt><dd>{{ option.noise_indoor_min_db == null ? 'Нет данных' : option.noise_indoor_min_db + ' дБ(А)' }}</dd>
              <dt>Инвертор</dt><dd>{{ option.is_inverter == null ? 'Нет данных' : option.is_inverter ? 'Да' : 'Нет' }}</dd>
              <dt>Wi-Fi</dt><dd>{{ option.wifi == null ? 'Нет данных' : wifiName[option.wifi] }}</dd>
            </dl>
            <p v-if="option.note">{{ option.note }}</p>
          </div>
        </li>
      </ul>
    </section>
  </section>
</template>
