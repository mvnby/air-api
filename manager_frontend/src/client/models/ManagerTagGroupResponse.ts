/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTagOptionResponse } from './ManagerTagOptionResponse';
export type ManagerTagGroupResponse = {
    id: number;
    title: string;
    slug: string;
    color: string;
    is_public: boolean;
    allow_multiple: boolean;
    tags: Array<ManagerTagOptionResponse>;
};

