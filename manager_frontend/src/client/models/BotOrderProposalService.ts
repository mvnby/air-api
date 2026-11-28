/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotOrderProposalDisplayLine } from './BotOrderProposalDisplayLine';
export type BotOrderProposalService = {
    title: string;
    description?: (string | null);
    quantity: number;
    unit_price: string;
    line_total: string;
    id: number;
    can_edit_quantity: boolean;
    can_edit_price: boolean;
    can_remove?: boolean;
    service_id: (number | null);
    unit: (string | null);
    display_lines?: Array<BotOrderProposalDisplayLine>;
};

