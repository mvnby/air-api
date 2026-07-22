/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type FeatureRuleResponse = {
    spec_key: string;
    operator: 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'contains' | 'exists';
    target_value?: any;
    is_active?: boolean;
    sort_order?: number;
    id: number;
    feature_id: number;
};

