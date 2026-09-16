import type { ManagerProductCollectionPlacementPayload } from "../../client";

export const placementLocations = [
  {
    key: "home/featured_products",
    label: "Главная · Основные подборки",
    surface: "home",
    slot: "featured_products",
  },
  {
    key: "home/after_featured",
    label: "Главная · После основных подборок",
    surface: "home",
    slot: "after_featured",
  },
  {
    key: "home/product_of_day",
    label: "Главная · Товар дня",
    surface: "home",
    slot: "product_of_day",
  },
  {
    key: "catalog/before_products",
    label: "Каталог · Перед товарами",
    surface: "catalog",
    slot: "before_products",
  },
  {
    key: "catalog/after_products",
    label: "Каталог · После товаров",
    surface: "catalog",
    slot: "after_products",
  },
] as const;

export function placementLabel(
  row: Pick<
    ManagerProductCollectionPlacementPayload,
    "surface_key" | "slot_key"
  >,
): string {
  return (
    placementLocations.find(
      (item) => item.surface === row.surface_key && item.slot === row.slot_key,
    )?.label ??
    (row.surface_key === "article"
      ? `Статья · ${row.slot_key}`
      : `${row.surface_key} / ${row.slot_key}`)
  );
}

export function placementLocationKey(
  row: ManagerProductCollectionPlacementPayload,
): string {
  if (row.surface_key === "article") return "article";
  return (
    placementLocations.find(
      (item) => item.surface === row.surface_key && item.slot === row.slot_key,
    )?.key ?? "custom"
  );
}

export function articleCollectionSnippet(slot: string): string {
  if (!/^[a-z0-9][a-z0-9_-]{0,79}$/.test(slot)) return "";
  return `import ArticleProductCollection from '../../components/mdx/ArticleProductCollection.astro';\n\n<ArticleProductCollection slot="${slot}" />`;
}

export function placementDateForInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}
