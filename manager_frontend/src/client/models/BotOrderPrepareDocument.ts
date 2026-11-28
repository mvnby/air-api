/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderPrepareDocument = {
    kind: string;
    document_type: ('offer' | 'invoice' | string);
    legal_entity_id: number;
    proposal_id: (number | null);
    receipt_note?: (string | null);
};

