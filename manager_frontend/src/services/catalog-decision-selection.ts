export type CatalogDecisionSelectionItem = {
  id: number;
  title: string;
};

type SelectionStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type StoredSelection = {
  expiresAt: number;
  items: CatalogDecisionSelectionItem[];
};

export const CATALOG_DECISION_SELECTION_STORAGE_KEY = 'manager:catalog-decision:selection:v1';
export const CATALOG_DECISION_SELECTION_TTL_MS = 5 * 60 * 1000;

const browserStorage = (): SelectionStorage | null => {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
};

const normalizedItems = (value: unknown): CatalogDecisionSelectionItem[] => {
  if (!Array.isArray(value)) return [];
  const seen = new Set<number>();
  return value.flatMap((item) => {
    const id = Number((item as Partial<CatalogDecisionSelectionItem>)?.id);
    const title = String((item as Partial<CatalogDecisionSelectionItem>)?.title || '').trim();
    if (!Number.isInteger(id) || id <= 0 || !title || seen.has(id)) return [];
    seen.add(id);
    return [{ id, title }];
  });
};

export const loadCatalogDecisionSelection = (
  storage: SelectionStorage | null = browserStorage(),
  now = Date.now(),
): CatalogDecisionSelectionItem[] => {
  try {
    const raw = storage?.getItem(CATALOG_DECISION_SELECTION_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<StoredSelection>;
    const expiresAt = Number(parsed.expiresAt);
    if (!Number.isFinite(expiresAt) || expiresAt <= now) {
      storage?.removeItem(CATALOG_DECISION_SELECTION_STORAGE_KEY);
      return [];
    }
    return normalizedItems(parsed.items);
  } catch {
    try {
      storage?.removeItem(CATALOG_DECISION_SELECTION_STORAGE_KEY);
    } catch {
      // The workspace remains usable when browser storage is unavailable.
    }
    return [];
  }
};

export const saveCatalogDecisionSelection = (
  items: CatalogDecisionSelectionItem[],
  storage: SelectionStorage | null = browserStorage(),
  now = Date.now(),
): void => {
  const normalized = normalizedItems(items);
  try {
    if (!normalized.length) {
      storage?.removeItem(CATALOG_DECISION_SELECTION_STORAGE_KEY);
      return;
    }
    storage?.setItem(CATALOG_DECISION_SELECTION_STORAGE_KEY, JSON.stringify({
      expiresAt: now + CATALOG_DECISION_SELECTION_TTL_MS,
      items: normalized,
    } satisfies StoredSelection));
  } catch {
    // Selection still lives in the current view even if session storage is blocked.
  }
};
