/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerProductCollectionPlacementResponse = {
    display_mode?: 'carousel' | 'grid' | 'tiles' | 'single';
    item_limit?: (number | null);
    grid_columns?: number;
    rotation_mode?: 'none' | 'daily';
    id: number;
    surface_key: string;
    slot_key: string;
    position: number;
    is_enabled: boolean;
    starts_at?: (string | null);
    ends_at?: (string | null);
};

