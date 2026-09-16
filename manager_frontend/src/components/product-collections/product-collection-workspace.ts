import type {
  ManagerProductCollectionCreate,
  ManagerProductCollectionItemResponse,
  ManagerProductCollectionPlacementPayload,
  ManagerProductCollectionPlacementResponse,
  ManagerProductCollectionResponse,
  ProductCollectionRuleConfig,
} from '../../client';
import { placementDateForInput } from './product-collection-placements';

export type CollectionForm = {
  slug: string;
  internal_name: string;
  public_title: string;
  public_description: string;
  public_badge: string;
  status: 'draft' | 'published' | 'archived';
  mode: 'manual' | 'automatic' | 'hybrid';
  sort_mode: 'recommended' | 'price_asc' | 'price_desc' | 'area_asc' | 'area_desc' | 'newest';
  rule_config: ProductCollectionRuleConfig;
  min_items: number;
  max_items: number;
  fallback_collection_id: number | null;
  starts_at: string;
  ends_at: string;
};

export const emptyRuleConfig = (): ProductCollectionRuleConfig => ({
  product_kinds: ['complete_split_system'], min_price: null, max_price: null,
  min_area_m2: null, max_area_m2: null, max_noise_min_db: null,
  max_heating_min_c: null, is_inverter: null, wifi_states: [], brand_ids: [],
  series_ids: [], colors: [], feature_ids: [], public_stock_states: [],
});

export const emptyCollectionForm = (): CollectionForm => ({
  slug: '', internal_name: '', public_title: '', public_description: '', public_badge: '',
  status: 'draft', mode: 'manual', sort_mode: 'recommended', rule_config: emptyRuleConfig(),
  min_items: 1, max_items: 6, fallback_collection_id: null, starts_at: '', ends_at: '',
});

export const dateTimeLocal = placementDateForInput;
export const apiDate = (value?: string | null) => value ? new Date(value).toISOString() : null;

export const collectionFormFrom = (collection: ManagerProductCollectionResponse): CollectionForm => ({
  slug: collection.slug, internal_name: collection.internal_name, public_title: collection.public_title,
  public_description: collection.public_description || '', public_badge: collection.public_badge || '',
  status: collection.status || 'draft', mode: collection.mode || 'manual',
  sort_mode: collection.sort_mode || 'recommended',
  rule_config: { ...emptyRuleConfig(), ...(collection.rule_config || {}) },
  min_items: collection.min_items || 1, max_items: collection.max_items || 6,
  fallback_collection_id: collection.fallback_collection_id || null,
  starts_at: dateTimeLocal(collection.starts_at), ends_at: dateTimeLocal(collection.ends_at),
});

export const collectionItemsFrom = (
  collection: ManagerProductCollectionResponse,
): ManagerProductCollectionItemResponse[] => (collection.items || [])
  .map(item => ({ ...item }))
  .sort((left, right) => left.position - right.position);

export const collectionPayload = (form: CollectionForm): ManagerProductCollectionCreate => ({
  slug: form.slug || null, internal_name: form.internal_name.trim(), public_title: form.public_title.trim(),
  public_description: form.public_description.trim() || null, public_badge: form.public_badge.trim() || null,
  status: form.status, mode: form.mode, sort_mode: form.sort_mode, rule_config: form.rule_config,
  min_items: Number(form.min_items), max_items: Number(form.max_items),
  fallback_collection_id: form.fallback_collection_id || null,
  starts_at: apiDate(form.starts_at), ends_at: apiDate(form.ends_at),
});

export const defaultPlacements = (): ManagerProductCollectionPlacementPayload[] => ([{
  surface_key: 'home', slot_key: 'featured_products', position: 0, is_enabled: true,
  starts_at: null, ends_at: null,
  display_mode: 'grid', grid_columns: 4, rotation_mode: 'none', item_limit: null,
}]);

export const placementPayloads = (
  placements: Array<ManagerProductCollectionPlacementPayload | ManagerProductCollectionPlacementResponse>,
): ManagerProductCollectionPlacementPayload[] => placements.map((placement, index) => ({
  surface_key: placement.surface_key, slot_key: placement.slot_key,
  position: placement.position ?? index, is_enabled: placement.is_enabled,
  starts_at: apiDate(placement.starts_at), ends_at: apiDate(placement.ends_at),
  display_mode: 'display_mode' in placement ? placement.display_mode : undefined,
  item_limit: 'item_limit' in placement ? placement.item_limit : undefined,
  grid_columns: 'grid_columns' in placement ? placement.grid_columns : undefined,
  rotation_mode: 'rotation_mode' in placement ? placement.rotation_mode : undefined,
}));

export const itemPayloads = (items: ManagerProductCollectionItemResponse[]) => items.map(item => ({
  product_id: item.product_id, is_pinned: item.is_pinned, editorial_note: item.editorial_note || null,
}));

export const statusLabel = (status?: string) => ({ draft: 'Черновик', published: 'Опубликована', archived: 'Архив' }[status || 'draft'] || status || 'Черновик');
export const kindLabel = (kind?: string | null) => ({ unknown: 'Тип не задан', complete_split_system: 'Готовая сплит-система', indoor_unit: 'Внутренний блок', outdoor_unit: 'Наружный блок', panel: 'Панель', accessory: 'Аксессуар', consumable: 'Расходник', other: 'Другое' }[kind || 'unknown'] || kind || 'Тип не задан');
