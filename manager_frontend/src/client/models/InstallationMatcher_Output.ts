/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type InstallationMatcher_Output = {
    product_kind?: 'complete_split_system' | 'multi_split_system';
    indoor_type?: ('wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | 'console' | null);
    work_kind?: 'standard' | 'prelaid_route';
    match_strategy?: 'strict' | 'capacity_only' | 'type_only';
    capacity_min_kw?: (string | null);
    capacity_max_kw?: (string | null);
    capacity_min_inclusive?: boolean;
    capacity_max_inclusive?: boolean;
    pipe_liquid?: (string | null);
    pipe_gas?: (string | null);
    weight_source?: ('weight_indoor' | 'weight_outdoor' | 'weight_indoor_package' | 'weight_outdoor_package' | null);
    weight_min_kg?: (string | null);
    weight_max_kg?: (string | null);
};

