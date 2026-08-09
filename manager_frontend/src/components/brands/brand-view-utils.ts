import type { SeriesContentBlockForm } from "./brand-form-types";

export const SORT_ORDER_STEP = 10;

export const getNextSortOrder = <T extends { sort_order?: number | null }>(
  items: T[],
) =>
  items.reduce((max, item) => Math.max(max, Number(item.sort_order || 0)), 0) +
  SORT_ORDER_STEP;

export const compactText = (value: string, maxLength = 160) => {
  const text = String(value || "")
    .replace(/\s+/g, " ")
    .trim();
  return text.length <= maxLength
    ? text
    : `${text.slice(0, maxLength - 1).trim()}…`;
};

export const moveItemById = <T extends { id: number }>(
  items: T[],
  draggedId: number,
  targetId: number,
) => {
  const sourceIndex = items.findIndex((item) => item.id === draggedId);
  const targetIndex = items.findIndex((item) => item.id === targetId);
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex)
    return items;
  const next = [...items];
  const [moved] = next.splice(sourceIndex, 1);
  if (!moved) return items;
  next.splice(targetIndex, 0, moved);
  return next;
};

export const withSortOrder = <T extends { sort_order: number }>(items: T[]) =>
  items.map((item, index) => ({
    ...item,
    sort_order: (index + 1) * SORT_ORDER_STEP,
  }));

export const getChangedSortItems = <
  T extends { id: number; sort_order: number },
>(
  previous: T[],
  next: T[],
) => {
  const previousOrder = new Map(
    previous.map((item) => [item.id, Number(item.sort_order || 0)]),
  );
  return next.filter(
    (item) => Number(item.sort_order || 0) !== previousOrder.get(item.id),
  );
};

export const normalizeTextList = (value: string) => {
  const seen = new Set<string>();
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
};

export const normalizeUrlList = (value: string[]) => {
  const seen = new Set<string>();
  return value
    .map((item) => String(item || "").trim())
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
};

export const normalizeContentBlocks = (blocks: SeriesContentBlockForm[]) =>
  blocks
    .map((block) => ({
      kind: block.kind || "text",
      title: String(block.title || "").trim() || undefined,
      text: String(block.text || "").trim() || undefined,
      image_url: String(block.image_url || "").trim() || undefined,
      layout: block.layout || "text_left",
    }))
    .filter((block) => block.title || block.text || block.image_url);
