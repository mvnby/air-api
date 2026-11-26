/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TenderLotMatch = {
    lot_key: string;
    state: 'match' | 'review' | 'excluded';
    reason: 'eligible' | 'excluded_place' | 'excluded_direction' | 'excluded_activity' | 'different_place' | 'different_direction' | 'different_activity' | 'unconfirmed_place' | 'unconfirmed_direction' | 'unconfirmed_activity';
};

