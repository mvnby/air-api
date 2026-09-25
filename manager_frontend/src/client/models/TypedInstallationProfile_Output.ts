/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TypedInstallationProfile_Output = {
    product_kind: string;
    indoor_type?: ('wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | 'console' | null);
    capacity_cooling_kw?: (string | null);
    indoor_unit_count?: (number | null);
    composition_note?: (string | null);
    pipe_liquid?: (string | null);
    pipe_gas?: (string | null);
    weight_indoor?: (string | null);
    weight_outdoor?: (string | null);
    weight_indoor_package?: (string | null);
    weight_outdoor_package?: (string | null);
    confirmed?: boolean;
};

