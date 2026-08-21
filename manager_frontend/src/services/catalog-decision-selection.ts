import type { ManagerAuthStatusResponse } from '../client';

export type CatalogDecisionSelectionItem = {
  id: number;
  title: string;
};

type SelectionStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type StoredSelection = {
  expiresAt: number;
  items: CatalogDecisionSelectionItem[];
};

type SelectionIdentity = Pick<
  ManagerAuthStatusResponse,
  'tenant_id' | 'staff_user_id' | 'username'
>;

export const CATALOG_DECISION_SELECTION_STORAGE_KEY_PREFIX = 'manager:catalog-decision:selection:v2';
export const CATALOG_DECISION_SELECTION_TTL_MS = 24 * 60 * 60 * 1000;

export const catalogDecisionSelectionStorageKey = (identity: SelectionIdentity): string => {
  const userKey = identity.staff_user_id
    ? `staff-${identity.staff_user_id}`
    : `user-${encodeURIComponent(identity.username.trim().toLowerCase())}`;
  return `${CATALOG_DECISION_SELECTION_STORAGE_KEY_PREFIX}:${identity.tenant_id}:${userKey}`;
};

const browserStorage = (): SelectionStorage | null => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
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
  storageKey: string,
  storage: SelectionStorage | null = browserStorage(),
  now = Date.now(),
): CatalogDecisionSelectionItem[] => {
  try {
    const raw = storage?.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<StoredSelection>;
    const expiresAt = Number(parsed.expiresAt);
    if (!Number.isFinite(expiresAt) || expiresAt <= now) {
      storage?.removeItem(storageKey);
      return [];
    }
    return normalizedItems(parsed.items);
  } catch {
    try {
      storage?.removeItem(storageKey);
    } catch {
      // The workspace remains usable when browser storage is unavailable.
    }
    return [];
  }
};

export const saveCatalogDecisionSelection = (
  items: CatalogDecisionSelectionItem[],
  storageKey: string,
  storage: SelectionStorage | null = browserStorage(),
  now = Date.now(),
): void => {
  const normalized = normalizedItems(items);
  try {
    if (!normalized.length) {
      storage?.removeItem(storageKey);
      return;
    }
    storage?.setItem(storageKey, JSON.stringify({
      expiresAt: now + CATALOG_DECISION_SELECTION_TTL_MS,
      items: normalized,
    } satisfies StoredSelection));
  } catch {
    // Selection still lives in the current view even if session storage is blocked.
  }
};
