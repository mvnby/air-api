<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { api, type Product } from '../api';
import { X, Save, Plus, Trash2, Edit3, Globe, Hash, Tag } from 'lucide-vue-next';
import { getApiErrorMessage, parseApiFieldErrors } from '../utils/api-errors';
import SpecKeyCombobox from './SpecKeyCombobox.vue';
import { specsTranslations } from '../utils/specsTranslations';

interface TagItem {
    id: number;
    title: string;
    slug: string;
}

interface TagGroupItem {
    id: number;
    title: string;
    slug: string;
    color: string;
    allow_multiple: boolean;
    tags: TagItem[];
}

const props = defineProps<{
    modelValue: boolean;
    product: Product | null;
}>();

const emit = defineEmits<{
    (e: 'update:modelValue', value: boolean): void;
    (e: 'success'): void;
}>();

const form = ref<any>({
    title: '',
    slug: '',
    price: 0,
    old_price: 0,
    is_published: true,
});

const specs = ref<{ key: string; value: string }[]>([]);
const selectedTagIds = ref<Set<number>>(new Set());
const loading = ref(false);
const formMessage = ref('');
const formServerErrors = ref<Record<string, string>>({});
const knownKeys = ref<string[]>([]);
const tagGroups = ref<TagGroupItem[]>([]);
const tagsLoading = ref(false);
const tagSearchQuery = ref('');
const vitebskQty = ref(0);
const supplierOffers = ref<any[]>([]);
const localStockSaving = ref(false);

const fetchKeys = async () => {
    try {
        const res = await api.getPublicSpecKeys();
        const combined = new Set([...Object.keys(specsTranslations), ...res.keys]);
        knownKeys.value = Array.from(combined);
    } catch (e) { console.error(e); }
};

const fetchTags = async () => {
    if (tagGroups.value.length > 0) return; // already loaded
    tagsLoading.value = true;
    try {
        tagGroups.value = await api.getAllTags();
    } catch (e) { console.error(e); }
    finally { tagsLoading.value = false; }
};

const filteredTagGroups = computed(() => {
    if (!tagSearchQuery.value.trim()) return tagGroups.value;
    const q = tagSearchQuery.value.toLowerCase().trim();
    return tagGroups.value
        .map(g => ({
            ...g,
            tags: g.tags.filter(t => t.title.toLowerCase().includes(q)),
        }))
        .filter(g => g.tags.length > 0);
});

const isTagSelected = (id: number) => selectedTagIds.value.has(id);

const toggleTag = (id: number) => {
    if (selectedTagIds.value.has(id)) {
        selectedTagIds.value.delete(id);
    } else {
        selectedTagIds.value.add(id);
    }
};

const colorMap: Record<string, string> = {
    primary: 'bg-blue-100 text-blue-800 border-blue-200',
    success: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    info: 'bg-cyan-100 text-cyan-800 border-cyan-200',
    warning: 'bg-amber-100 text-amber-800 border-amber-200',
    danger: 'bg-red-100 text-red-800 border-red-200',
    secondary: 'bg-gray-100 text-gray-700 border-gray-200',
};

const getColorClasses = (color: string) => colorMap[color] || colorMap.secondary;
const selectedColorClasses: Record<string, string> = {
    primary: 'bg-blue-600 text-white border-blue-600',
    success: 'bg-emerald-600 text-white border-emerald-600',
    info: 'bg-cyan-600 text-white border-cyan-600',
    warning: 'bg-amber-600 text-white border-amber-600',
    danger: 'bg-red-600 text-white border-red-600',
    secondary: 'bg-gray-600 text-white border-gray-600',
};
const getSelectedColorClasses = (color: string) => selectedColorClasses[color] || selectedColorClasses.secondary;

watch(() => props.modelValue, (val) => {
    if (val && props.product) {
        formMessage.value = '';
        formServerErrors.value = {};
        form.value = {
            title: props.product.title,
            slug: props.product.slug,
            price: props.product.price,
            old_price: props.product.old_price,
            is_published: props.product.is_published,
        };
        
        // Convert specs object to array
        const s = props.product.specs || {};
        specs.value = Object.entries(s).map(([key, value]) => {
            let sVal = String(value);
            const config = specsTranslations[key];
            if (config?.type === 'number' && config.unit) {
                // remove unit, handle case and spaces
                sVal = sVal.replace(new RegExp(config.unit + '$', 'i'), '').trim();
                const match = sVal.match(/^-?\d*[.,]?\d*/);
                sVal = match && match[0] ? match[0].replace(',', '.') : '';
            }
            return { key, value: sVal };
        });
        
        // Load tags
        const productTags = (props.product as any).tags || [];
        selectedTagIds.value = new Set(productTags.map((t: any) => t.id));
        tagSearchQuery.value = '';
        
        if (knownKeys.value.length === 0) fetchKeys();
        fetchTags();
        vitebskQty.value = Number((props.product as any).vitebsk_qty || 0);
        loadSupplierOffers();
    }
});

const loadSupplierOffers = async () => {
    if (!props.product) return;
    try {
        const res = await api.getProductSupplierOffers(props.product.id);
        supplierOffers.value = res.items || [];
    } catch (e) {
        console.error(e);
        supplierOffers.value = [];
    }
};

const addRow = () => specs.value.push({ key: '', value: '' });
const removeRow = (index: number) => specs.value.splice(index, 1);

const close = () => emit('update:modelValue', false);

const saveLocalStock = async () => {
    if (!props.product) return;
    localStockSaving.value = true;
    formMessage.value = '';
    try {
        await api.upsertProductLocalStock(props.product.id, { qty: Number(vitebskQty.value || 0) });
        emit('success');
    } catch (e) {
        formMessage.value = `Ошибка при обновлении склада: ${getApiErrorMessage(e)}`;
    } finally {
        localStockSaving.value = false;
    }
};

const save = async () => {
    if (!props.product) return;
    
    // Process specs back to object
    const validSpecs: Record<string, string> = {};
    for (const row of specs.value) {
        if (row.key.trim()) {
            let finalValue = row.value;
            const config = specsTranslations[row.key.trim()];
            if (config?.type === 'number' && config.unit && finalValue.toString().trim() !== '') {
                finalValue = `${finalValue} ${config.unit}`.trim();
            } else if (config?.type === 'boolean') {
                finalValue = (row.value === 'true') ? 'true' : 'false';
            }
            validSpecs[row.key.trim()] = finalValue.toString().trim();
        }
    }

    loading.value = true;
    formMessage.value = '';
    formServerErrors.value = {};
    try {
        const updateData = {
            ...form.value,
            specs: validSpecs,
            tag_ids: Array.from(selectedTagIds.value),
        };
        await api.updateProduct(props.product.id, updateData);
        emit('success');
        close();
    } catch (e) {
        const parsed = parseApiFieldErrors(e, [
            'title',
            'slug',
            'price',
            'old_price',
            'is_published',
            'specs',
            'tag_ids',
        ]);
        formServerErrors.value = parsed.fieldErrors;
        formMessage.value = parsed.message || `Ошибка при сохранении: ${getApiErrorMessage(e)}`;
        console.error(e);
    } finally {
        loading.value = false;
    }
};
</script>

<template>
    <div v-if="modelValue" class="product-edit-modal fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60] p-4" @click.self="close">
        <div class="bg-slate-50 dark:bg-slate-900 rounded-2xl w-full max-w-5xl flex flex-col max-h-[90vh] shadow-2xl border border-gray-100 dark:border-slate-800 overflow-hidden">
            <!-- Header -->
            <header class="p-5 border-b dark:border-slate-800 flex justify-between items-center bg-slate-100/50 dark:bg-slate-800/50">
                <div class="flex items-center gap-3">
                    <div class="p-2 bg-teal-100 rounded-lg text-teal-700">
                        <Edit3 class="w-5 h-5" />
                    </div>
                    <div>
                        <h2 class="text-lg font-bold text-gray-900 dark:text-white">Редактирование товара</h2>
                        <p class="text-xs text-gray-500 dark:text-slate-400 font-medium uppercase tracking-wider">ID: {{ product?.id }}</p>
                    </div>
                </div>
                <button @click="close" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all">
                    <X class="w-5 h-5" />
                </button>
            </header>
            <div v-if="formMessage" class="mx-6 mt-4 rounded-xl border border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">
                {{ formMessage }}
            </div>
            
            <div class="flex-1 overflow-y-auto p-6">
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Column 1: Basic Info -->
                    <section class="space-y-5">
                        <h3 class="text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest">Основные данные</h3>
                        
                        <div>
                            <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Название модели</label>
                            <input 
                                v-model="form.title" 
                                type="text"
                                class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-gray-900 dark:text-slate-100 font-medium text-sm"
                                :class="formServerErrors.title ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                placeholder="Напр: LG ARTCOOL Gallery"
                            />
                            <p v-if="formServerErrors.title" class="mt-1 text-xs text-red-600">{{ formServerErrors.title }}</p>
                        </div>

                        <div>
                            <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1 flex justify-between items-center">
                                <span>Slug (URL путь)</span>
                                <Globe class="w-3.5 h-3.5 text-gray-400 dark:text-slate-500" />
                            </label>
                            <input 
                                v-model="form.slug" 
                                type="text"
                                class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-sm font-mono text-gray-600 dark:text-slate-300"
                                :class="formServerErrors.slug ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                placeholder="lg-artcool-gallery"
                            />
                            <p v-if="formServerErrors.slug" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ formServerErrors.slug }}</p>
                        </div>

                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Цена (BYN)</label>
                                <div class="relative">
                                    <input 
                                        v-model.number="form.price" 
                                        type="number"
                                        class="w-full pl-3 pr-10 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all font-bold text-teal-700 dark:text-teal-400 text-sm"
                                        :class="formServerErrors.price ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                    />
                                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 text-xs">руб.</span>
                                </div>
                                <p v-if="formServerErrors.price" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ formServerErrors.price }}</p>
                            </div>
                            <div>
                                <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1 line-through decoration-gray-400 dark:decoration-slate-600">Старая цена</label>
                                <div class="relative">
                                    <input 
                                        v-model.number="form.old_price" 
                                        type="number"
                                        class="w-full pl-3 pr-10 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-gray-500 dark:text-slate-400 text-sm"
                                        :class="formServerErrors.old_price ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
                                    />
                                    <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 text-xs">руб.</span>
                                </div>
                                <p v-if="formServerErrors.old_price" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ formServerErrors.old_price }}</p>
                            </div>
                        </div>

                        <div class="flex items-center gap-2 pt-1">
                             <label class="relative inline-flex items-center cursor-pointer">
                                <input type="checkbox" v-model="form.is_published" class="sr-only peer">
                                <div class="w-11 h-6 bg-gray-200 dark:bg-slate-700 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-900 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 dark:after:border-slate-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-600"></div>
                                <span class="ms-3 text-sm font-semibold text-gray-700 dark:text-slate-300">Опубликовано</span>
                            </label>
                        </div>

                        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 space-y-3">
                            <h4 class="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">Supply</h4>
                            <div class="flex items-end gap-2">
                                <div class="flex-1">
                                    <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Склад Витебск (шт)</label>
                                    <input v-model.number="vitebskQty" type="number" min="0" class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-xl text-sm" />
                                </div>
                                <button
                                    @click="saveLocalStock"
                                    :disabled="localStockSaving"
                                    class="px-3 py-2 rounded-xl bg-teal-600 text-white text-sm font-semibold disabled:opacity-50"
                                >
                                    {{ localStockSaving ? 'Сохранение...' : 'Сохранить' }}
                                </button>
                            </div>
                            <div class="max-h-40 overflow-y-auto space-y-2">
                                <div v-if="supplierOffers.length === 0" class="text-xs text-gray-500 dark:text-slate-400">Нет привязанных офферов</div>
                                <div v-for="offer in supplierOffers" :key="`${offer.supplier_id}-${offer.external_id}`" class="text-xs border border-gray-100 dark:border-slate-700 rounded-lg p-2 bg-slate-50 dark:bg-slate-900/40">
                                    <div class="font-semibold text-gray-700 dark:text-slate-200">{{ offer.supplier_name || offer.supplier_id }} / {{ offer.external_id }}</div>
                                    <div class="text-gray-500 dark:text-slate-400">
                                        qty: {{ offer.qty }} | wholesale: {{ offer.wholesale_value ?? '—' }} {{ offer.wholesale_currency || '' }} | rrc: {{ offer.rrc_byn ?? '—' }}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>

                    <!-- Column 2: Specs -->
                    <section class="space-y-5">
                        <div class="flex justify-between items-center">
                            <h3 class="text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                                 Характеристики
                            </h3>
                            <button @click="addRow" class="text-xs bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 px-2.5 py-1 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700 text-teal-600 dark:text-teal-400 font-bold flex items-center gap-1 transition-colors shadow-sm">
                                <Plus class="w-3 h-3" /> Добавить
                            </button>
                        </div>

                        <div class="space-y-2 bg-slate-100/50 dark:bg-slate-800/50 p-3 rounded-2xl border border-gray-100 dark:border-slate-800 max-h-[400px] overflow-y-auto">
                            <div v-for="(row, idx) in specs" :key="idx" class="flex gap-1.5 items-start group">
                                <div class="relative flex-1">
                                    <SpecKeyCombobox 
                                        v-model="row.key" 
                                        :known-keys="knownKeys" 
                                    />
                                </div>
                                
                                <div class="flex-1">
                                    <template v-if="specsTranslations[row.key]?.type === 'boolean'">
                                        <div class="flex items-center h-[38px]">
                                            <button 
                                                type="button"
                                                @click="row.value = (row.value === 'true') ? 'false' : 'true'"
                                                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2"
                                                :class="(row.value === 'true') ? 'bg-teal-600' : 'bg-gray-200 dark:bg-slate-700'"
                                                role="switch"
                                                :aria-checked="row.value === 'true'"
                                            >
                                                <span class="sr-only">Toggle boolean</span>
                                                <span 
                                                    aria-hidden="true" 
                                                    class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                                                    :class="(row.value === 'true') ? 'translate-x-5' : 'translate-x-0'"
                                                />
                                            </button>
                                            <span class="ml-3 text-sm font-medium text-gray-900 dark:text-slate-200">
                                                {{ (row.value === 'true') ? 'Да' : 'Нет' }}
                                            </span>
                                        </div>
                                    </template>
                                    
                                    <template v-else-if="specsTranslations[row.key]?.type === 'select'">
                                        <select 
                                            v-model="row.value"
                                            class="w-full h-[38px] border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all text-gray-900 dark:text-slate-200 shadow-inner"
                                        >
                                            <option value="" disabled>Выберите значение</option>
                                            <option v-for="opt in specsTranslations[row.key]?.options || []" :key="opt" :value="opt">
                                                {{
                                                    row.key === 'wifi_ready'
                                                        ? (opt === 'true' ? 'Да (встроен)' : (opt === 'ready' ? 'Ready (модуль отдельно)' : 'Нет'))
                                                        : opt
                                                }}
                                            </option>
                                        </select>
                                    </template>
                                    
                                    <template v-else-if="specsTranslations[row.key]?.type === 'number'">
                                        <div class="flex h-[38px] rounded-lg shadow-inner">
                                            <input 
                                                type="number"
                                                v-model="row.value" 
                                                placeholder="Значение" 
                                                class="flex-1 min-w-0 block w-full border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-gray-900 dark:text-slate-200 rounded-none rounded-l-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all"
                                            />
                                            <span v-if="specsTranslations[row.key]?.unit" class="inline-flex items-center px-2.5 rounded-r-lg border border-l-0 border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-700 text-gray-500 dark:text-slate-300 text-xs">
                                                {{ specsTranslations[row.key]?.unit }}
                                            </span>
                                        </div>
                                    </template>
                                    
                                    <template v-else>
                                        <input 
                                            type="text"
                                            v-model="row.value" 
                                            placeholder="Значение" 
                                            class="w-full h-[38px] border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-all text-gray-900 dark:text-slate-200 dark:placeholder-slate-500 shadow-inner"
                                        />
                                    </template>
                                </div>
                                
                                <button @click="removeRow(idx)" class="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all">
                                    <Trash2 class="w-3.5 h-3.5" />
                                </button>
                            </div>
                            
                            <div v-if="specs.length === 0" class="text-center py-6 text-gray-400 dark:text-slate-500">
                                 <Hash class="w-6 h-6 mx-auto mb-1.5 opacity-20" />
                                 <p class="text-xs">Нет характеристик</p>
                            </div>
                        </div>
                    </section>
                </div>

                <details class="mt-6 border border-gray-200 dark:border-slate-700 rounded-xl bg-slate-50 dark:bg-slate-800/50 group">
                    <summary class="cursor-pointer p-4 font-bold text-gray-700 dark:text-slate-300 flex justify-between items-center outline-none">
                        <span class="flex items-center gap-2"><Tag class="w-4 h-4 text-gray-400 dark:text-slate-500"/> Теги ({{ selectedTagIds.size }} выбрано)</span>
                    </summary>
                    <div class="p-4 border-t border-gray-200 dark:border-slate-700">
                        <input 
                            v-model="tagSearchQuery"
                            type="text"
                            placeholder="Поиск тега..."
                            class="w-full mb-4 px-3 py-2 bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-xl focus:bg-white focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-sm dark:text-slate-200 dark:placeholder-slate-500"
                        />

                        <div class="bg-gray-50/50 dark:bg-slate-800/50 rounded-xl border border-gray-100 dark:border-slate-800 max-h-[300px] overflow-y-auto">
                            <div v-if="tagsLoading" class="p-6 text-center text-gray-400 text-sm">Загрузка...</div>
                            <div v-else-if="filteredTagGroups.length === 0" class="p-6 text-center text-gray-400 text-sm">Нет тегов</div>
                            <div v-else>
                                <div v-for="group in filteredTagGroups" :key="group.id" class="p-3 border-b border-gray-100 dark:border-slate-800 last:border-b-0">
                                    <p class="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">{{ group.title }}</p>
                                    <div class="flex flex-wrap gap-1.5">
                                        <button 
                                            v-for="tag in group.tags" 
                                            :key="tag.id"
                                            @click="toggleTag(tag.id)"
                                            class="px-2.5 py-1 rounded-full text-xs font-semibold border cursor-pointer transition-all"
                                            :class="isTagSelected(tag.id) ? getSelectedColorClasses(group.color) : getColorClasses(group.color)"
                                        >
                                            {{ tag.title }}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </details>
            </div>
            
            <!-- Footer -->
            <footer class="p-5 border-t dark:border-slate-800 bg-slate-100/50 dark:bg-slate-800/50 flex justify-end gap-3">
                <button @click="close" class="px-5 py-2 text-sm font-bold text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 rounded-xl transition-all">
                    Отмена
                </button>
                <button 
                    @click="save" 
                    :disabled="loading"
                    class="px-8 py-2 bg-teal-600 text-white rounded-xl shadow-lg shadow-teal-700/20 hover:bg-teal-700 disabled:opacity-50 flex items-center gap-2 text-sm font-bold transition-all transform hover:-translate-y-0.5 active:translate-y-0"
                >
                    <div v-if="loading" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    <Save v-else class="w-4 h-4" />
                    Сохранить
                </button>
            </footer>
        </div>
    </div>
</template>

<style scoped>
:global(.dark) .product-edit-modal .text-gray-400 {
  color: #94a3b8 !important;
}

:global(.dark) .product-edit-modal .text-gray-500 {
  color: #94a3b8 !important;
}

:global(.dark) .product-edit-modal .text-gray-600 {
  color: #cbd5e1 !important;
}

:global(.dark) .product-edit-modal .text-gray-700 {
  color: #e2e8f0 !important;
}

:global(.dark) .product-edit-modal .bg-gray-50\/50,
:global(.dark) .product-edit-modal .bg-gray-50 {
  background-color: #0f172a !important;
}

:global(.dark) .product-edit-modal .border-gray-100,
:global(.dark) .product-edit-modal .border-gray-200 {
  border-color: #334155 !important;
}

:global(.dark) .product-edit-modal footer button:first-child {
  color: #cbd5e1 !important;
}

:global(.dark) .product-edit-modal input::placeholder {
  color: #64748b !important;
}
</style>
