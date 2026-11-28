/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotOrderInstallationOption } from './BotOrderInstallationOption';
import type { BotOrderProposalProduct } from './BotOrderProposalProduct';
import type { BotOrderProposalService } from './BotOrderProposalService';
export type BotOrderProposal = {
    id: (number | null);
    name: string;
    status: string;
    is_selected: boolean;
    is_archived: boolean;
    total_amount: string;
    equipment_total: string;
    services_total: string;
    can_select: boolean;
    can_add_equipment: boolean;
    product_lines: Array<BotOrderProposalProduct>;
    service_lines: Array<BotOrderProposalService>;
    installation_options: Array<BotOrderInstallationOption>;
};

