/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type InstallationMatcher_Input = {
    product_kind?: string;
    indoor_type: 'wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | 'console';
    capacity_min_kw?: (number | string | null);
    capacity_max_kw?: (number | string | null);
    pipe_liquid?: (string | null);
    pipe_gas?: (string | null);
    weight_source?: ('weight_indoor' | 'weight_outdoor' | 'weight_indoor_package' | 'weight_outdoor_package' | null);
    weight_min_kg?: (number | string | null);
    weight_max_kg?: (number | string | null);
};

