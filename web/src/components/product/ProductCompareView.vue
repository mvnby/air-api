<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getProductBySlug, resolveImageUrl } from "../../utils/api";
import {
  buildCompareUrl,
  normalizeCompareItems,
  PRODUCT_COMPARE_STORAGE_KEY,
  readCompareSlugsFromSearch,
  type ProductCompareItem,
} from "../../utils/product-compare";

type Product = Record<string, any>;

const loading = ref(true);
const error = ref("");
const usingSavedData = ref(false);
const products = ref<Product[]>([]);

const toBool = (value: unknown) => value === true || value === "true" || value === 1 || value === "1";
const specValue = (product: Product, keys: string[]) => {
  for (const key of keys) {
    const value = product?.specs?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
};

const compressor = (product: Product) => {
  const normalized = String(specValue(product, ["compressor_type_norm"]) || "").toLowerCase();
  if (normalized === "full_dc") return "Full DC Inverter";
  if (normalized === "inverter" || product.is_inverter) return "Инвертор";
  if (normalized === "on_off" || product.is_inverter === false) return "On/Off";
  return "Не указано";
};

const wifi = (product: Product) => {
  const value = specValue(product, ["wifi_ready", "wifi"]);
  if (value === "ready") return "Опция";
  return toBool(value) || value === "builtin" ? "Встроенный" : "Нет данных";
};

const heating = (product: Product) => {
  const value = specValue(product, ["min_temp_heat", "temp_range_heat"]);
  return value ? String(value) : "Не указано";
};

const noise = (product: Product) => {
  const value = specValue(product, ["noise_indoor_min", "indoor_noise", "noise_level"]);
  return value ? `${value}${String(value).includes("дБ") ? "" : " дБ"}` : "Не указано";
};

const availability = (product: Product) => {
  const qty = Number(product.vitebsk_qty || 0) + Number(product.minsk_qty || 0);
  if (qty > 0 || product.availability_status === "in_stock_now") return "В наличии";
  if (product.availability_status === "available_2_3_days") return "Доступно через 2–3 дня";
  return "Уточнить наличие";
};

const rows = computed(() => [
  { label: "Цена", values: products.value.map((product) => product.price ? `${Number(product.price).toLocaleString("ru-RU")} BYN` : "Уточнить") },
  { label: "Площадь", values: products.value.map((product) => product.specs?.area_m2 ? `до ${product.specs.area_m2} м²` : "Не указано") },
  { label: "Компрессор", values: products.value.map(compressor) },
  { label: "Wi-Fi", values: products.value.map(wifi) },
  { label: "Обогрев", values: products.value.map(heating) },
  { label: "Минимальный шум", values: products.value.map(noise) },
  { label: "Наличие", values: products.value.map(availability) },
]);

const storeProducts = () => {
  const items = products.value.map((product) => ({ slug: product.slug, title: product.title, snapshot: product }));
  localStorage.setItem(PRODUCT_COMPARE_STORAGE_KEY, JSON.stringify(normalizeCompareItems(items)));
  window.dispatchEvent(new CustomEvent("mvn:compare-change"));
  window.history.replaceState({}, "", buildCompareUrl(items));
};

const removeProduct = (slug: string) => {
  products.value = products.value.filter((product) => product.slug !== slug);
  storeProducts();
};

const clearProducts = () => {
  products.value = [];
  storeProducts();
};

onMounted(async () => {
  const fromSearch = readCompareSlugsFromSearch(window.location.search);
  let fromStorage: ProductCompareItem[] = [];
  try {
    fromStorage = normalizeCompareItems(JSON.parse(localStorage.getItem(PRODUCT_COMPARE_STORAGE_KEY) || "[]"));
  } catch {
    localStorage.removeItem(PRODUCT_COMPARE_STORAGE_KEY);
  }
  const slugs = fromSearch.length ? fromSearch : fromStorage.map((item) => item.slug);

  if (slugs.length === 0) {
    loading.value = false;
    return;
  }

  try {
    const results = await Promise.all(slugs.map(async (slug) => {
      const fresh = await getProductBySlug(slug);
      if (fresh?.slug) return fresh;
      const stored = fromStorage.find((item) => item.slug === slug)?.snapshot;
      if (stored?.slug) usingSavedData.value = true;
      return stored || null;
    }));
    products.value = results.filter((product): product is Product => Boolean(product?.slug));
    if (products.value.length === 0) error.value = "Не удалось загрузить выбранные модели.";
    storeProducts();
  } catch {
    error.value = "Не удалось обновить данные моделей. Попробуйте ещё раз позже.";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="compare-view">
    <div v-if="loading" class="compare-status" aria-live="polite">
      <span class="material-icons-round spin" aria-hidden="true">refresh</span>
      Загружаем актуальные характеристики…
    </div>

    <div v-else-if="error" class="compare-status compare-status--error" role="alert">
      <span class="material-icons-round" aria-hidden="true">error_outline</span>
      {{ error }}
    </div>

    <div v-else-if="products.length === 0" class="compare-empty">
      <span class="material-icons-round" aria-hidden="true">compare_arrows</span>
      <h2>Модели пока не выбраны</h2>
      <p>Добавьте от двух до трёх кондиционеров из каталога.</p>
      <a href="/catalog/">Перейти в каталог <span class="material-icons-round" aria-hidden="true">arrow_forward</span></a>
    </div>

    <template v-else>
      <div class="compare-toolbar">
        <p>
          Сравниваем {{ products.length }} из 3 моделей
          <span v-if="usingSavedData">· сохранённые данные</span>
        </p>
        <button type="button" @click="clearProducts">Очистить</button>
      </div>

      <div class="compare-table-wrap" tabindex="0" aria-label="Таблица сравнения моделей">
        <table>
          <thead>
            <tr>
              <th scope="col">Модель</th>
              <th v-for="product in products" :key="product.slug" scope="col">
                <div class="compare-product">
                  <img :src="resolveImageUrl(product.card_image || product.main_image)" :alt="product.title" width="320" height="240" />
                  <a :href="`/product/${product.slug}/`">{{ product.title }}</a>
                  <button type="button" :aria-label="`Убрать ${product.title} из сравнения`" @click="removeProduct(product.slug)">
                    <span class="material-icons-round" aria-hidden="true">close</span>Убрать
                  </button>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.label">
              <th scope="row">{{ row.label }}</th>
              <td v-for="(value, index) in row.values" :key="`${row.label}-${products[index].slug}`">{{ value }}</td>
            </tr>
            <tr>
              <th scope="row">Подробнее</th>
              <td v-for="product in products" :key="`details-${product.slug}`">
                <a class="compare-details" :href="`/product/${product.slug}/`">Открыть модель</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="compare-note">Сравнение использует текущие данные каталога. Условия монтажа и окончательную мощность проверяем отдельно для помещения.</p>
    </template>
  </div>
</template>

<style scoped>
.compare-view { margin-top: 2rem; }
.compare-status,
.compare-empty {
  display: grid;
  min-height: 260px;
  place-items: center;
  align-content: center;
  gap: 0.75rem;
  padding: 2rem;
  border: 1px solid var(--panel-glass-border);
  border-radius: 8px;
  background: var(--panel-glass-bg);
  color: var(--text-muted);
  text-align: center;
}
.compare-empty .material-icons-round { color: var(--primary); font-size: 2.25rem; }
.compare-empty h2 { color: var(--text); font-size: 1.45rem; }
.compare-empty a,
.compare-details { display: inline-flex; align-items: center; gap: 0.35rem; color: var(--primary); font-weight: 800; text-decoration: none; }
.compare-status--error { color: var(--error-text); }
.spin { animation: spin 0.8s linear infinite; }
.compare-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1rem; }
.compare-toolbar p { color: var(--text-muted); }
.compare-toolbar button { min-height: 42px; padding: 0.55rem 0.8rem; border: 1px solid var(--panel-chip-border); border-radius: 8px; background: var(--panel-chip-bg); color: var(--text); font-weight: 700; cursor: pointer; }
.compare-table-wrap { overflow-x: auto; border: 1px solid var(--panel-glass-border); border-radius: 8px; background: var(--panel-glass-bg); }
.compare-table-wrap:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
table { width: 100%; min-width: 760px; border-collapse: collapse; }
th, td { min-width: 200px; padding: 1rem; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th:first-child, td:first-child { min-width: 150px; width: 150px; color: var(--text-muted); font-size: 0.82rem; }
thead th { color: var(--text); }
.compare-product { display: grid; gap: 0.65rem; }
.compare-product img { width: 100%; height: 130px; object-fit: contain; }
.compare-product > a { color: var(--text); font-size: 0.9rem; line-height: 1.35; text-decoration: none; }
.compare-product button { display: inline-flex; align-items: center; gap: 0.3rem; width: fit-content; min-height: 40px; border: 0; background: transparent; color: var(--text-muted); cursor: pointer; }
.compare-product button .material-icons-round { font-size: 1rem; }
.compare-product a:focus-visible,
.compare-product button:focus-visible,
.compare-toolbar button:focus-visible,
.compare-details:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.compare-note { margin: 1rem 0 0; color: var(--text-muted); font-size: 0.8rem; line-height: 1.5; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 640px) {
  .compare-view { margin-top: 1.25rem; }
  th, td { min-width: 170px; padding: 0.8rem; }
  .compare-product img { height: 110px; }
}
@media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
</style>
