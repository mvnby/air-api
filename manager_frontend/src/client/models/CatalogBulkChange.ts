/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CatalogBulkChange = {
    kind: 'relations' | 'specs' | 'features' | 'publication' | 'category';
    brand_id?: (number | null);
    series_id?: (number | null);
    specs?: Record<string, any>;
    spec_mode?: 'set' | 'fill_empty' | 'remove';
    feature_ids?: Array<number>;
    feature_mode?: 'add' | 'hide' | 'inherit';
    is_published?: (boolean | null);
    category?: ('cat-household' | 'cat-multi' | 'cat-industrial' | null);
};

