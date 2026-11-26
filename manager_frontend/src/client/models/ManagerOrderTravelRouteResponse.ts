/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderTravelLeg } from './OrderTravelLeg';
export type ManagerOrderTravelRouteResponse = {
    provider: string;
    origin: string;
    destination: string;
    approximate_destination: boolean;
    outbound: OrderTravelLeg;
    inbound: OrderTravelLeg;
    total: OrderTravelLeg;
};

