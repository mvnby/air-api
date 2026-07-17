/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotNameplateRecognitionResponse = {
    order_id: number;
    unit_type?: ('indoor_unit' | 'outdoor_unit' | null);
    raw_text: string;
    extracted?: Record<string, any>;
    validation_flags?: Record<string, any>;
    merge_preview?: Record<string, any>;
};

