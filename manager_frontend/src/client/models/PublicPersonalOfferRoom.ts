/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublicPersonalOfferInstallation } from './PublicPersonalOfferInstallation';
import type { PublicPersonalOfferOption } from './PublicPersonalOfferOption';
export type PublicPersonalOfferRoom = {
    title: string;
    selection_mode?: 'choice' | 'package';
    equipment_total_byn?: (string | null);
    total_with_installation_byn?: (string | null);
    installation: PublicPersonalOfferInstallation;
    options: Array<PublicPersonalOfferOption>;
};

