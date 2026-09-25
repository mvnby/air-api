/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TypedInstallationProfile_Input = {
    product_kind: string;
    indoor_type?: ('wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | 'console' | null);
    capacity_cooling_kw?: (number | string | null);
    indoor_unit_count?: (number | null);
    composition_note?: (string | null);
    pipe_liquid?: (string | null);
    pipe_gas?: (string | null);
    weight_indoor?: (number | string | null);
    weight_outdoor?: (number | string | null);
    weight_indoor_package?: (number | string | null);
    weight_outdoor_package?: (number | string | null);
    confirmed?: boolean;
};

