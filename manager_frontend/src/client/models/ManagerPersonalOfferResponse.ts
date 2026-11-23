/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerPersonalOfferPublished } from './ManagerPersonalOfferPublished';
import type { PersonalOfferRoomInput_Output } from './PersonalOfferRoomInput_Output';
export type ManagerPersonalOfferResponse = {
    order_id?: (number | null);
    expires_at: string;
    rooms: Array<PersonalOfferRoomInput_Output>;
    id: number;
    version: number;
    published: (ManagerPersonalOfferPublished | null);
};

