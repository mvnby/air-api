/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MultiSplitComponent } from './MultiSplitComponent';
export type MultiSplitPreviewResponse = {
    status: 'confirmed' | 'requires_specialist' | 'incompatible';
    explanation: string;
    composition_complete: boolean;
    equipment_total_byn: number;
    installation_total_byn?: null;
    components: Array<MultiSplitComponent>;
    source_url?: (string | null);
    source_version?: (string | null);
};

