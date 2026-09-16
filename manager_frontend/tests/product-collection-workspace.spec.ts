import { describe, expect, it } from 'vitest';
import { collectionItemsFrom, dateTimeLocal, placementPayloads } from '../src/components/product-collections/product-collection-workspace';

describe('product collection workspace mappers', () => {
  it('preserves placement presentation and the explicitly saved slot order', () => {
    expect(placementPayloads([{ id: 1, surface_key: 'home', slot_key: 'featured_products', position: 7, is_enabled: true, display_mode: 'grid', grid_columns: 4, item_limit: 8, rotation_mode: 'none', starts_at: '2026-09-20T09:00:00Z' } as any])).toMatchObject([{ position: 7, display_mode: 'grid', grid_columns: 4, item_limit: 8, rotation_mode: 'none' }]);
  });

  it('formats scheduled instants for a local datetime control without UTC slicing', () => {
    const value = dateTimeLocal('2026-09-20T09:00:00Z');
    expect(value).toMatch(/^2026-09-20T\d\d:\d\d$/);
  });

  it('copies and sorts item rows before the editor mutates them', () => {
    const source: any = {
      items: [
        { product_id: 2, position: 1, is_pinned: false, editorial_note: null },
        { product_id: 1, position: 0, is_pinned: true, editorial_note: 'Исходная' },
      ],
    };
    const items = collectionItemsFrom(source);
    items[0]!.is_pinned = false;
    items[0]!.editorial_note = 'Изменена';
    expect(items.map(item => item.product_id)).toEqual([1, 2]);
    expect(source.items[1]).toMatchObject({ is_pinned: true, editorial_note: 'Исходная' });
  });
});
