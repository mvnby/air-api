/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderMarketCrmLink } from './TenderMarketCrmLink';
import type { TenderMarketProfileMatch } from './TenderMarketProfileMatch';
export type TenderMarketItem = {
    id: number;
    title: string;
    source: string;
    source_url: string;
    deadline_at?: (string | null);
    crm_link?: (TenderMarketCrmLink | null);
    profiles: Array<TenderMarketProfileMatch>;
};

