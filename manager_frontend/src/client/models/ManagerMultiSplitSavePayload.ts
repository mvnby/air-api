/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MultiSplitComponent } from './MultiSplitComponent';
import type { MultiSplitRoomInput } from './MultiSplitRoomInput';
export type ManagerMultiSplitSavePayload = {
    outdoor_product_id: number;
    rooms: Array<MultiSplitRoomInput>;
    proposal_id?: (number | null);
    expected_status: 'confirmed' | 'requires_specialist' | 'incompatible';
    expected_components: Array<MultiSplitComponent>;
};

