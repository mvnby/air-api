/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderUpdateLine = {
    kind: string;
    proposal_id: (number | null);
    line_kind: 'product' | 'service';
    line_id: number;
    quantity?: (number | null);
    unit_price?: (number | string | null);
};

