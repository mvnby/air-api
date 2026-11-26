/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type InstallationMaterialPriceUpdate = {
    title: string;
    supplier: string;
    unit: 'm' | 'm2' | 'piece' | 'set' | 'kg' | 'l' | 'roll';
    pack_quantity: (number | string);
    pack_price_byn: (number | string);
    checked_on: string;
    source_url?: (string | null);
    note?: string;
    expected_version: number;
};

