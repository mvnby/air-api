/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderPlace } from './TenderPlace';
export type TenderSearchProfile = {
    name: string;
    mode?: 'broad' | 'strict';
    included_places?: Array<TenderPlace>;
    excluded_places?: Array<TenderPlace>;
    included_directions?: Array<'air_conditioning' | 'ventilation' | 'refrigeration'>;
    excluded_directions?: Array<'air_conditioning' | 'ventilation' | 'refrigeration'>;
    activity_combinations?: Array<Array<'maintenance' | 'diagnostics' | 'repair' | 'supply' | 'installation'>>;
    excluded_activities?: Array<'maintenance' | 'diagnostics' | 'repair' | 'supply' | 'installation'>;
};

