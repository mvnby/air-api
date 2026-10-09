<script setup lang="ts">
import { ref, toRef } from 'vue';
import MaintenanceObservationsPanel from '../maintenance-observations/MaintenanceObservationsPanel.vue';
import type { ManagerCatalogCustomerItemResponse } from '../../client';
import EquipmentAttachmentsPanel from '../equipment/EquipmentAttachmentsPanel.vue';
import EquipmentWarrantyPanel from '../equipment/EquipmentWarrantyPanel.vue';
import { useCustomerEquipmentPanel } from './useCustomerEquipmentPanel';
const maintenanceBranchId = ref<number | null>(null);
const props = defineProps<{ customer: ManagerCatalogCustomerItemResponse }>();
const { equipment, includeArchivedEquipment, equipmentLoading, loadCustomerEquipment, openEquipmentCreateForm, equipmentError, showEquipmentForm, saveEquipment, equipmentFormTitle, equipmentForm, EQUIPMENT_SOURCE_OPTIONS, equipmentSaving, editingEquipmentId, selectedEquipmentId, selectEquipment, equipmentTitle, warrantyStatusClass, equipmentWarrantyView, equipmentSubtitle, equipmentBranchLabel, equipmentSourceLabel, formatDateOnly, openEquipmentEditForm, equipmentActionId, toggleEquipmentArchive, equipmentHistoryLoading, selectedEquipmentDetail, openHistoryCreateForm, updateSelectedCoverage, openComponentCreateForm, showComponentForm, saveEquipmentComponent, componentForm, EQUIPMENT_COMPONENT_OPTIONS, canManagePlatform, componentSaving, editingComponentId, componentTypeLabel, componentTitle, componentLine, openComponentEditForm, componentActionId, toggleEquipmentComponentArchive, showHistoryForm, createEquipmentHistory, historyForm, EQUIPMENT_EVENT_OPTIONS, historySaving, equipmentEventLabel, formatDate, historyLine } = useCustomerEquipmentPanel(toRef(props, 'customer'));
</script>
<template>
<section class="customer-section">
  <div class="mb-4 space-y-2">
    <label class="field-label">Замечания по объекту<select v-model="maintenanceBranchId" class="field-input"><option :value="null">Все объекты клиента</option><option v-for="branch in customer.branches || []" :key="branch.id" :value="branch.id">{{ branch.name || branch.delivery_address || `Объект #${branch.id}` }}</option></select></label>
    <MaintenanceObservationsPanel :customer-id="customer.id" :customer-branch-id="maintenanceBranchId" />
  </div>
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 class="flex items-center gap-2 text-lg font-bold">
              <span class="material-icons-round text-brand-500">precision_manufacturing</span>
              Оборудование клиента
              <span v-if="equipment.length" class="flex h-6 min-w-6 items-center justify-center rounded-full bg-brand-500/20 px-2 text-xs text-brand-400">{{ equipment.length }}</span>
            </h2>
            <div class="flex flex-wrap items-center gap-2">
              <label class="inline-flex items-center gap-2 rounded-xl border border-[var(--mv-border)] px-3 py-2 text-xs text-[var(--mv-text-muted)]">
                <input v-model="includeArchivedEquipment" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
                Архив
              </label>
              <button class="btn-mini-outline" type="button" :disabled="equipmentLoading" @click="loadCustomerEquipment">
                Обновить
              </button>
              <button class="btn-mini" type="button" @click="openEquipmentCreateForm">
                Создать оборудование
              </button>
            </div>
          </div>

          <p v-if="equipmentError" class="mb-3 rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-200">
            {{ equipmentError }}
          </p>

          <form v-if="showEquipmentForm" class="mb-4 rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-4" @submit.prevent="saveEquipment">
            <h3 class="mb-3 break-words text-sm font-semibold text-[var(--mv-text)]">{{ equipmentFormTitle }}</h3>
            <div class="grid gap-3 md:grid-cols-3">
              <label class="field-label">
                Филиал
                <select v-model="equipmentForm.customer_branch_id" class="field-input">
                  <option :value="null">Без филиала</option>
                  <option v-for="branch in customer.branches || []" :key="branch.id" :value="branch.id">
                    {{ branch.name || branch.delivery_address || `Филиал #${branch.id}` }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Источник
                <select v-model="equipmentForm.equipment_source" class="field-input">
                  <option v-for="option in EQUIPMENT_SOURCE_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Тип
                <input v-model="equipmentForm.equipment_type" class="field-input" placeholder="hvac, chiller..." />
              </label>
              <label class="field-label">
                ID товара каталога
                <input v-model="equipmentForm.catalog_product_id" class="field-input" inputmode="numeric" placeholder="Можно оставить пустым" />
              </label>
              <label class="field-label">
                ID исходного заказа
                <input v-model="equipmentForm.source_order_id" class="field-input" inputmode="numeric" placeholder="Заказ продажи/монтажа" />
              </label>
              <label class="field-label">
                Название
                <input v-model="equipmentForm.display_name" class="field-input" placeholder="Кондиционер серверной" />
              </label>
              <label class="field-label">
                Бренд
                <input v-model="equipmentForm.brand" class="field-input" placeholder="Gree, LG..." />
              </label>
              <label class="field-label">
                Модель
                <input v-model="equipmentForm.model" class="field-input" placeholder="Модель блока" />
              </label>
              <label class="field-label">
                Серийный номер
                <input v-model="equipmentForm.serial" class="field-input" placeholder="SN..." />
              </label>
              <label class="field-label">
                Инвентарный номер
                <input v-model="equipmentForm.inventory_number" class="field-input" placeholder="Инв. номер клиента" />
              </label>
              <label class="field-label">
                Локация
                <input v-model="equipmentForm.location_hint" class="field-input" placeholder="Серверная, 2 этаж" />
              </label>
              <label class="field-label">
                Хладагент
                <input v-model="equipmentForm.refrigerant_type" class="field-input" placeholder="R32, R410A" />
              </label>
              <label class="field-label">
                Дата установки
                <input v-model="equipmentForm.installed_at" class="field-input" type="date" />
              </label>
              <label class="field-label">
                Ввод в эксплуатацию
                <input v-model="equipmentForm.commissioned_at" class="field-input" type="date" />
              </label>
              <label class="field-label">
                Гарантия с
                <input v-model="equipmentForm.warranty_started_at" class="field-input" type="date" />
              </label>
              <label class="field-label">
                Гарантия до
                <input v-model="equipmentForm.warranty_expires_at" class="field-input" type="date" />
              </label>
              <label class="field-label md:col-span-3">
                Условия гарантии
                <textarea v-model="equipmentForm.warranty_terms" class="field-input min-h-[72px]" placeholder="Например: 24 месяца на оборудование, 12 месяцев на монтаж. Гарантия сохраняется при ежегодном ТО." />
              </label>
              <label class="field-label md:col-span-3">
                Заметки
                <textarea v-model="equipmentForm.notes" class="field-input min-h-[72px]" placeholder="Особенности доступа, состояние, монтаж..." />
              </label>
            </div>
            <div class="mt-3 flex flex-wrap justify-end gap-2">
              <button class="btn-mini-outline" type="button" :disabled="equipmentSaving" @click="showEquipmentForm = false">Отмена</button>
              <button class="btn-mini" type="submit" :disabled="equipmentSaving">
                {{ equipmentSaving ? 'Сохраняем...' : (editingEquipmentId ? 'Сохранить' : 'Создать') }}
              </button>
            </div>
          </form>

          <div v-if="equipmentLoading" class="rounded-2xl border border-dashed border-[var(--mv-border)] p-5 text-sm text-[var(--mv-text-muted)]">
            Загрузка оборудования...
          </div>
          <div v-else-if="equipment.length" class="grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            <div class="space-y-3">
              <article
                v-for="item in equipment"
                :key="item.id"
                class="rounded-xl border p-4 shadow-sm transition"
                :class="selectedEquipmentId === item.id ? 'border-brand-400 bg-brand-500/10' : 'border-[var(--mv-border)] bg-[var(--mv-surface)] hover:border-brand-400/60'"
              >
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <button
                    type="button"
                    class="min-w-0 flex-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                    :aria-pressed="selectedEquipmentId === item.id"
                    @click="selectEquipment(item.id)"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <p class="break-words text-sm font-semibold text-[var(--mv-text)]">{{ equipmentTitle(item) }}</p>
                      <span class="rounded-full px-2 py-0.5 text-[11px] font-semibold" :class="warrantyStatusClass(equipmentWarrantyView(item).status)">
                        {{ equipmentWarrantyView(item).label }}
                      </span>
                      <span v-if="item.is_archived" class="rounded-full bg-slate-500/20 px-2 py-0.5 text-[11px] font-semibold text-slate-400">Архив</span>
                    </div>
                    <p class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ equipmentSubtitle(item) }}</p>
                    <p class="mt-1 text-xs text-[var(--mv-text-muted)]">{{ equipmentBranchLabel(item.customer_branch_id) }} · {{ equipmentSourceLabel(item.equipment_source) }}</p>
                    <p v-if="equipmentWarrantyView(item).expiresAt" class="mt-1 text-xs text-[var(--mv-text-muted)]">Ближайшее окончание {{ formatDateOnly(equipmentWarrantyView(item).expiresAt) }}</p>
                  </button>
                  <div class="flex shrink-0 flex-wrap gap-2">
                    <button class="btn-mini-outline text-xs" type="button" @click="openEquipmentEditForm(item)">Править</button>
                    <button class="btn-mini-outline text-xs" type="button" :disabled="equipmentActionId === item.id" @click="toggleEquipmentArchive(item)">
                      {{ equipmentActionId === item.id ? '...' : (item.is_archived ? 'Вернуть' : 'Архив') }}
                    </button>
                  </div>
                </div>
              </article>
            </div>

            <div class="rounded-2xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-4">
              <div v-if="equipmentHistoryLoading" class="text-sm text-[var(--mv-text-muted)]">Загрузка истории...</div>
              <template v-else-if="selectedEquipmentDetail">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div class="min-w-0">
                    <p class="break-words text-base font-semibold">{{ equipmentTitle(selectedEquipmentDetail) }}</p>
                    <p class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ equipmentSubtitle(selectedEquipmentDetail) }}</p>
                    <div class="mt-2 flex flex-wrap gap-2 text-xs">
                      <span class="rounded-full px-2 py-0.5 font-semibold" :class="warrantyStatusClass(equipmentWarrantyView(selectedEquipmentDetail).status)">
                        {{ equipmentWarrantyView(selectedEquipmentDetail).label }}
                      </span>
                      <span class="rounded-full bg-slate-500/20 px-2 py-0.5 text-slate-400">{{ equipmentSourceLabel(selectedEquipmentDetail.equipment_source) }}</span>
                    </div>
                    <div class="mt-3 grid gap-2 text-xs text-[var(--mv-text-muted)] sm:grid-cols-2">
                      <p v-if="selectedEquipmentDetail.catalog_product_id">Товар каталога: #{{ selectedEquipmentDetail.catalog_product_id }}</p>
                      <p v-if="selectedEquipmentDetail.source_order_id">Исходный заказ: #{{ selectedEquipmentDetail.source_order_id }}</p>
                      <p v-if="selectedEquipmentDetail.installed_at">Установка: {{ formatDateOnly(selectedEquipmentDetail.installed_at) }}</p>
                      <p v-if="selectedEquipmentDetail.commissioned_at">Ввод: {{ formatDateOnly(selectedEquipmentDetail.commissioned_at) }}</p>
                      <template v-if="!(selectedEquipmentDetail.coverages || []).length">
                        <p v-if="selectedEquipmentDetail.warranty_started_at">Ранее указано, начало: {{ formatDateOnly(selectedEquipmentDetail.warranty_started_at) }}</p>
                        <p v-if="selectedEquipmentDetail.warranty_expires_at">Ранее указано, окончание: {{ formatDateOnly(selectedEquipmentDetail.warranty_expires_at) }}</p>
                        <p v-if="selectedEquipmentDetail.warranty_terms" class="break-words sm:col-span-2">Ранее указанные условия: {{ selectedEquipmentDetail.warranty_terms }}</p>
                      </template>
                    </div>
                  </div>
                  <button class="btn-mini whitespace-nowrap text-xs" type="button" @click="openHistoryCreateForm">Добавить событие</button>
                </div>

                <EquipmentWarrantyPanel
                  :warranty-mode="selectedEquipmentDetail.warranty_mode"
                  :coverages="selectedEquipmentDetail.coverages || []"
                  :linked-orders="selectedEquipmentDetail.linked_orders || []"
                  @updated="updateSelectedCoverage"
                />

                <EquipmentAttachmentsPanel :equipment-id="selectedEquipmentDetail.id" />

                <div class="mt-4 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p class="text-sm font-semibold text-[var(--mv-text)]">Состав оборудования</p>
                      <p class="text-xs text-[var(--mv-text-muted)]">Внутренний блок, наружный блок и серийные номера</p>
                    </div>
                    <button class="btn-mini-outline text-xs" type="button" @click="openComponentCreateForm">
                      Добавить блок
                    </button>
                  </div>

                  <form v-if="showComponentForm" class="mt-3 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-3" @submit.prevent="saveEquipmentComponent">
                    <div class="grid gap-3 md:grid-cols-2">
                      <label class="field-label">
                        Тип блока
                        <select v-model="componentForm.component_type" class="field-input">
                          <option v-for="option in EQUIPMENT_COMPONENT_OPTIONS" :key="option.value" :value="option.value">
                            {{ option.label }}
                          </option>
                        </select>
                      </label>
                      <label class="field-label">
                        Название
                        <input v-model="componentForm.title" class="field-input" placeholder="Например: внутренний блок спальня" />
                      </label>
                      <label class="field-label">
                        Бренд
                        <input v-model="componentForm.brand" class="field-input" placeholder="TCL, Gree..." />
                      </label>
                      <label class="field-label">
                        Модель
                        <input v-model="componentForm.model" class="field-input" placeholder="Модель блока" />
                      </label>
                      <label class="field-label">
                        Серийный номер
                        <input v-model="componentForm.serial" class="field-input" placeholder="SN..." />
                      </label>
                      <label class="field-label">
                        Инвентарный номер
                        <input v-model="componentForm.inventory_number" class="field-input" placeholder="Если ведется у клиента" />
                      </label>
                      <label class="field-label">
                        ID товара каталога
                        <input v-model="componentForm.catalog_product_id" class="field-input" inputmode="numeric" placeholder="Опционально" />
                      </label>
                      <template v-if="canManagePlatform">
                        <label class="field-label">
                          ID поставщика
                          <input v-model="componentForm.supplier_id" class="field-input" inputmode="numeric" placeholder="Опционально" />
                        </label>
                        <label class="field-label">
                          Накладная поставщика
                          <input v-model="componentForm.supplier_invoice_number" class="field-input" placeholder="Номер документа" />
                        </label>
                        <label class="field-label">
                          Дата накладной
                          <input v-model="componentForm.supplier_invoice_date" class="field-input" type="date" />
                        </label>
                      </template>
                      <label class="field-label md:col-span-2">
                        Заметки
                        <textarea v-model="componentForm.notes" class="field-input min-h-[58px]" />
                      </label>
                    </div>
                    <div class="mt-3 flex flex-wrap justify-end gap-2">
                      <button class="btn-mini-outline" type="button" :disabled="componentSaving" @click="showComponentForm = false">Отмена</button>
                      <button class="btn-mini" type="submit" :disabled="componentSaving">
                        {{ componentSaving ? 'Сохраняем...' : (editingComponentId ? 'Сохранить блок' : 'Добавить блок') }}
                      </button>
                    </div>
                  </form>

                  <div class="mt-3 space-y-2">
                    <div
                      v-for="component in selectedEquipmentDetail.components || []"
                      :key="component.id"
                      class="rounded-xl border border-[var(--mv-border)] bg-[var(--mv-surface)] p-3 text-sm"
                      :class="component.is_archived ? 'opacity-60' : ''"
                    >
                      <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div class="min-w-0">
                          <div class="flex flex-wrap items-center gap-2">
                            <span class="rounded-full bg-brand-500/10 px-2 py-0.5 text-xs font-semibold text-brand-400">{{ componentTypeLabel(component.component_type) }}</span>
                            <span v-if="component.is_archived" class="rounded-full bg-slate-500/20 px-2 py-0.5 text-xs font-semibold text-slate-400">Архив</span>
                          </div>
                          <p class="mt-2 break-words font-semibold text-[var(--mv-text)]">{{ componentTitle(component) }}</p>
                          <p class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ componentLine(component) }}</p>
                          <p v-if="component.notes" class="mt-1 break-words text-xs text-[var(--mv-text-muted)]">{{ component.notes }}</p>
                        </div>
                        <div class="flex shrink-0 flex-wrap gap-2">
                          <button class="btn-mini-outline text-xs" type="button" @click="openComponentEditForm(component)">Править</button>
                          <button class="btn-mini-outline text-xs" type="button" :disabled="componentActionId === component.id" @click="toggleEquipmentComponentArchive(component)">
                            {{ componentActionId === component.id ? '...' : (component.is_archived ? 'Вернуть' : 'Архив') }}
                          </button>
                        </div>
                      </div>
                    </div>
                    <div v-if="!(selectedEquipmentDetail.components || []).length" class="rounded-xl border border-dashed border-[var(--mv-border)] px-3 py-4 text-center text-sm text-[var(--mv-text-muted)]">
                      Блоки и серийные номера пока не добавлены
                    </div>
                  </div>
                </div>

                <form v-if="showHistoryForm" class="mt-4 rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3" @submit.prevent="createEquipmentHistory">
                  <div class="grid gap-3 md:grid-cols-2">
                    <label class="field-label">
                      Тип события
                      <select v-model="historyForm.event_type" class="field-input">
                        <option v-for="option in EQUIPMENT_EVENT_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                      </select>
                    </label>
                    <label class="field-label">
                      Дата
                      <input v-model="historyForm.event_date" class="field-input" type="date" />
                    </label>
                    <label v-if="historyForm.event_type === 'maintenance'" class="field-label md:col-span-2">
                      Кто выполнил ТО
                      <select v-model="historyForm.maintenance_provider" class="field-input" required>
                        <option value="mvn">MVN</option>
                        <option value="authorized">Авторизованный сервис</option>
                        <option value="external">Сторонний исполнитель</option>
                      </select>
                    </label>
                    <label class="field-label md:col-span-2">
                      Жалоба / причина
                      <textarea v-model="historyForm.complaint_snapshot" class="field-input min-h-[58px]" />
                    </label>
                    <label class="field-label">
                      Диагностика
                      <textarea v-model="historyForm.diagnostic_result" class="field-input min-h-[70px]" />
                    </label>
                    <label class="field-label">
                      Рекомендация
                      <textarea v-model="historyForm.repair_recommendation" class="field-input min-h-[70px]" />
                    </label>
                    <label class="field-label">
                      Хладагент
                      <input v-model="historyForm.refrigerant_type" class="field-input" />
                    </label>
                    <label class="field-label">
                      Количество
                      <input v-model="historyForm.refrigerant_amount" class="field-input" />
                    </label>
                    <label class="inline-flex items-center gap-2 text-xs text-[var(--mv-text-muted)] md:col-span-2">
                      <input v-model="historyForm.not_repairable" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
                      Оборудование не ремонтируется
                    </label>
                    <label class="field-label md:col-span-2">
                      Причина / заметки
                      <textarea v-model="historyForm.not_repairable_reason" class="field-input min-h-[58px]" placeholder="Причина неремонтопригодности" />
                    </label>
                    <label class="field-label md:col-span-2">
                      Внутренние заметки
                      <textarea v-model="historyForm.notes" class="field-input min-h-[58px]" />
                    </label>
                  </div>
                  <div class="mt-3 flex flex-wrap justify-end gap-2">
                    <button class="btn-mini-outline" type="button" :disabled="historySaving" @click="showHistoryForm = false">Отмена</button>
                    <button class="btn-mini" type="submit" :disabled="historySaving">
                      {{ historySaving ? 'Добавляем...' : 'Добавить' }}
                    </button>
                  </div>
                </form>

                <div class="mt-4 space-y-2">
                  <div
                    v-for="entry in selectedEquipmentDetail.recent_history || []"
                    :key="entry.id"
                    class="rounded-xl border border-[var(--mv-border)] bg-[var(--mv-panel)] p-3 text-sm"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="rounded-full bg-brand-500/10 px-2 py-0.5 text-xs font-semibold text-brand-400">{{ equipmentEventLabel(entry.event_type) }}</span>
                      <span class="text-xs text-[var(--mv-text-muted)]">{{ formatDate(entry.event_date) }}</span>
                      <span v-if="entry.order_id" class="text-xs text-[var(--mv-text-muted)]">Заказ #{{ entry.order_id }}</span>
                    </div>
                    <p class="mt-2 break-words text-[var(--mv-text-muted)]">{{ historyLine(entry) }}</p>
                  </div>
                  <div v-if="!(selectedEquipmentDetail.recent_history || []).length" class="rounded-xl border border-dashed border-[var(--mv-border)] px-3 py-4 text-center text-sm text-[var(--mv-text-muted)]">
                    История обслуживания пока пустая
                  </div>
                </div>
              </template>
              <div v-else class="text-sm text-[var(--mv-text-muted)]">Выберите оборудование слева.</div>
            </div>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-[var(--mv-border)] py-5 text-center text-sm italic text-[var(--mv-text-muted)]">
            Оборудование пока не заведено
          </div>
        </section>
</template>
<style scoped src="../../styles/customer-workspace.css"></style>
