<script setup lang="ts">
import { Globe } from 'lucide-vue-next';
import type { Product, ProductUpdate } from '../../api';

type Category = NonNullable<Product['catalog_category']>;
type MainForm = {
    title: string;
    slug: string;
    price: number;
    old_price: number | null;
    is_published: boolean;
    product_kind: NonNullable<ProductUpdate['product_kind']>;
    catalog_category_override: Category | null;
};
const form = defineModel<MainForm>({ required: true });
const emit = defineEmits<{ (e: 'category-change'): void }>();
defineProps<{ errors: Record<string, string>; currentCategory?: Category | null }>();
const categories: { value: Category | null; label: string }[] = [
    { value: 'cat-household', label: 'Бытовые' },
    { value: 'cat-multi', label: 'Мульти-сплит' },
    { value: 'cat-industrial', label: 'Полупромышленные' },
    { value: null, label: 'Авто' },
];
const categoryLabel = (category: Category) => categories.find(item => item.value === category)?.label;
</script>

<template>
<div class="border-b border-gray-100 pb-4 dark:border-slate-800">
    <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Основное</p>
    <h2 class="mt-1 text-xl font-bold text-gray-950 dark:text-white">Название, цена и группа каталога</h2>
</div>

<div>
    <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Название модели</label>
    <input
        v-model="form.title"
        type="text"
        class="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-gray-900 dark:text-slate-100 font-medium text-sm"
        :class="errors.title ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
        placeholder="Напр: LG ARTCOOL Gallery"
    />
    <p v-if="errors.title" class="mt-1 text-xs text-red-600">{{ errors.title }}</p>
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
        :class="errors.slug ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
        placeholder="lg-artcool-gallery"
    />
    <p v-if="errors.slug" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ errors.slug }}</p>
</div>

<div class="grid grid-cols-2 gap-3">
    <div>
        <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1">Цена (BYN)</label>
        <div class="relative">
            <input
                v-model.number="form.price"
                type="number"
                class="w-full pl-3 pr-10 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all font-bold text-teal-700 dark:text-teal-400 text-sm"
                :class="errors.price ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
            />
            <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 text-xs">BYN</span>
        </div>
        <p v-if="errors.price" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ errors.price }}</p>
    </div>
    <div>
        <label class="block text-sm font-semibold text-gray-700 dark:text-slate-300 mb-1 line-through decoration-gray-400 dark:decoration-slate-600">Старая цена</label>
        <div class="relative">
            <input
                v-model.number="form.old_price"
                type="number"
                class="w-full pl-3 pr-10 py-2 bg-slate-100 dark:bg-slate-800 border rounded-xl focus:bg-white dark:focus:bg-slate-700 focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 outline-none transition-all text-gray-500 dark:text-slate-400 text-sm"
                :class="errors.old_price ? 'border-red-400 dark:border-red-800 focus:border-red-500' : 'border-gray-200 dark:border-slate-700'"
            />
            <span class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-slate-500 text-xs">BYN</span>
        </div>
        <p v-if="errors.old_price" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ errors.old_price }}</p>
    </div>
</div>

<div class="flex items-center gap-2 pt-1">
     <label class="relative inline-flex items-center cursor-pointer">
        <input type="checkbox" v-model="form.is_published" class="sr-only peer">
        <div class="w-11 h-6 bg-gray-200 dark:bg-slate-700 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-900 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 dark:after:border-slate-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-600"></div>
        <span class="ms-3 text-sm font-semibold text-gray-700 dark:text-slate-300">Опубликовано</span>
    </label>
</div>
<label class="block space-y-1">
    <span class="text-sm font-semibold text-gray-700 dark:text-slate-300">Канонический тип товара</span>
    <select v-model="form.product_kind" class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800">
        <option value="unknown">Не задан</option>
        <option value="complete_split_system">Готовая сплит-система</option>
        <option value="indoor_unit">Внутренний блок</option>
        <option value="outdoor_unit">Наружный блок</option>
        <option value="panel">Панель</option>
        <option value="accessory">Аксессуар</option>
        <option value="consumable">Расходный материал</option>
        <option value="other">Другое</option>
    </select>
    <p class="text-[11px] text-gray-500 dark:text-slate-400">От этого поля зависит допуск товара в потребительские витрины.</p>
    <p v-if="errors.product_kind" role="alert" class="text-xs text-red-600 dark:text-red-400">{{ errors.product_kind }}</p>
</label>
<fieldset class="space-y-2" data-testid="product-catalog-category">
    <legend class="text-sm font-semibold text-gray-700 dark:text-slate-300">Группа каталога</legend>
    <div class="flex flex-wrap gap-2">
        <button
            v-for="category in categories"
            :key="category.value || 'auto'"
            type="button"
            :aria-pressed="form.catalog_category_override === category.value"
            class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
            :class="form.catalog_category_override === category.value
                ? 'border-teal-600 bg-teal-600 text-white'
                : 'border-gray-200 bg-white text-gray-700 hover:border-teal-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'"
            @click="form.catalog_category_override = category.value; emit('category-change')"
        >{{ category.label }}</button>
    </div>
    <p v-if="form.catalog_category_override" class="text-xs text-gray-500 dark:text-slate-400">Ручной выбор сохранится при повторном импорте.</p>
    <p v-else class="text-xs text-gray-500 dark:text-slate-400">
        <template v-if="currentCategory">Сейчас в каталоге: {{ categoryLabel(currentCategory) }}. </template>
        При сохранении группа определяется по характеристикам товара.
    </p>
    <p v-if="errors.catalog_category_override" role="alert" class="text-xs text-red-600 dark:text-red-400">{{ errors.catalog_category_override }}</p>
</fieldset>
</template>
