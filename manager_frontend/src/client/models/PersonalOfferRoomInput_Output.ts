/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PersonalOfferInstallationInput_Output } from './PersonalOfferInstallationInput_Output';
import type { PersonalOfferOptionInput_Output } from './PersonalOfferOptionInput_Output';
export type PersonalOfferRoomInput_Output = {
    title?: (string | null);
    selection_mode?: 'choice' | 'package';
    show_total?: boolean;
    installation: PersonalOfferInstallationInput_Output;
    options: Array<PersonalOfferOptionInput_Output>;
};

