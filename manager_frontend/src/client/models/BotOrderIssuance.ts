/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderIssuance = {
    document_id: number;
    state: 'ready' | 'reserved' | 'blocked' | 'issued';
    revision: (string | null);
    reason: (string | null);
    document_type: string;
    legal_entity_name: (string | null);
    can_download_pdf: boolean;
};

