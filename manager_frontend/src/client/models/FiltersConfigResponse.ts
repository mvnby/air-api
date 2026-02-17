/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FilterRange } from './FilterRange';
import type { FilterTagOption } from './FilterTagOption';
export type FiltersConfigResponse = {
    price: FilterRange;
    area: FilterRange;
    brands?: Array<FilterTagOption>;
    expert_tags?: Array<FilterTagOption>;
};

