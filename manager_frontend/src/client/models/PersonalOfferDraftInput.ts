/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PersonalOfferRoomInput_Input } from './PersonalOfferRoomInput_Input';
export type PersonalOfferDraftInput = {
    order_id?: (number | null);
    /**
     * Внутреннее название для списка Manager.
     */
    title?: (string | null);
    expires_at: string;
    rooms: Array<PersonalOfferRoomInput_Input>;
};

