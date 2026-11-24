/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PersonalOfferInstallationInput_Input } from './PersonalOfferInstallationInput_Input';
import type { PersonalOfferOptionInput_Input } from './PersonalOfferOptionInput_Input';
export type PersonalOfferRoomInput_Input = {
    title?: (string | null);
    selection_mode?: 'choice' | 'package';
    show_total?: boolean;
    installation: PersonalOfferInstallationInput_Input;
    options: Array<PersonalOfferOptionInput_Input>;
};

