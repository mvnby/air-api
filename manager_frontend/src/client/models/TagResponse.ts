/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TagGroupResponse } from './TagGroupResponse';
export type TagResponse = {
    id: number;
    title: string;
    slug: string;
    is_public?: boolean;
    group?: (TagGroupResponse | null);
    group_title?: (string | null);
};

