<script setup lang="ts">
import { formatMoney } from '../model/document-formatters';
import type { WaybillProductLine } from '../model/document-types';
import {
  addWaybillComponent,
  lineLogisticsHasMismatch,
  lineLogisticsPerParentTotal,
  rebalanceWaybillLine,
  removeWaybillComponent,
  updateWaybillQuantity,
  updateWaybillUnitPrice,
} from '../model/waybill-logistics';

defineProps<{ lines: WaybillProductLine[] }>();
</script>

<template>
  <div class="rounded-xl border border-teal-200 bg-white p-3 dark:border-teal-800/70 dark:bg-slate-900/70">
    <div class="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 3: состав накладной</p>
        <p class="text-[11px] text-slate-500 dark:text-slate-400">{{ lines.length }} товар. поз. в активном предложении</p>
      </div>
    </div>

    <div v-if="lines.length" class="space-y-3">
      <div
        v-for="(line, lineIndex) in lines"
        :key="`waybill-line-${line.product_id}-${lineIndex}`"
        class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/60 dark:bg-slate-800/40"
      >
        <div class="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{{ line.product_query || 'Товар' }}</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              {{ line.logistics_components?.length || 0 }} поз. · {{ formatMoney(line.price) }} за комплект · кол-во {{ line.quantity }}
            </p>
          </div>
          <span
            class="w-fit rounded-lg px-2 py-1 text-xs font-semibold"
            :class="lineLogisticsHasMismatch(line) ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' : 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300'"
          >
            {{ lineLogisticsHasMismatch(line) ? 'Проверьте сумму' : 'Сумма совпадает' }}
          </span>
        </div>

        <div class="space-y-2">
          <div
            v-for="(component, componentIndex) in line.logistics_components || []"
            :key="`waybill-component-${line.product_id}-${componentIndex}`"
            class="grid gap-2 rounded-lg border border-white bg-white p-2 dark:border-slate-700/60 dark:bg-slate-900/80 md:grid-cols-[1.4fr_100px_70px_80px_95px_32px]"
          >
            <textarea v-model="component.title" class="field-input min-h-[38px] resize-none text-xs" rows="1" placeholder="Название позиции" />
            <input v-model="component.country" class="field-input h-9 text-xs" placeholder="Страна" />
            <input v-model="component.unit" class="field-input h-9 text-xs" placeholder="Ед." />
            <input
              :value="component.quantity_per_parent"
              type="number"
              min="1"
              class="field-input h-9 text-xs"
              title="Количество на комплект"
              @input="updateWaybillQuantity(line, componentIndex, ($event.target as HTMLInputElement).value)"
            />
            <input
              :value="component.unit_price"
              type="number"
              min="0"
              step="0.01"
              class="field-input h-9 text-xs"
              title="Цена за единицу"
              @input="updateWaybillUnitPrice(line, componentIndex, ($event.target as HTMLInputElement).value)"
            />
            <button
              type="button"
              class="flex h-9 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30"
              @click="removeWaybillComponent(line, componentIndex)"
            >
              <span class="material-icons-round text-[18px]">delete</span>
            </button>
            <select v-model="component.kind" class="field-input h-9 text-xs md:col-span-2" @change="rebalanceWaybillLine(line, null)">
              <option value="indoor">внутренний блок</option>
              <option value="outdoor">наружный блок</option>
              <option value="accessory">аксессуар</option>
              <option value="other">прочее</option>
            </select>
            <div class="flex items-center text-xs font-semibold text-slate-600 dark:text-slate-300 md:col-span-4">
              По строке: {{ formatMoney(component.unit_price * component.quantity_per_parent * line.quantity) }}
            </div>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-2">
            <p v-if="lineLogisticsHasMismatch(line)" class="text-xs font-semibold text-amber-700 dark:text-amber-300">
              Состав: {{ formatMoney(lineLogisticsPerParentTotal(line)) }}, товар: {{ formatMoney(line.price) }}.
            </p>
            <span v-else class="text-xs text-teal-700 dark:text-teal-300">Состав: {{ formatMoney(lineLogisticsPerParentTotal(line)) }}.</span>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              @click="addWaybillComponent(line)"
            >
              + позиция
            </button>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-4 text-center text-xs font-semibold text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-300">
      В активном предложении нет товаров для накладной.
    </div>
  </div>
</template>
