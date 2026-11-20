/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OrderTechnicalActPrepared = {
    order_id: number;
    site_id: number;
    equipment_ids: Array<number>;
    document_id: number;
    document_type: 'technical_inspection_act' | 'defect_act';
    status: string;
    revision: string;
    manager_url: string;
};

