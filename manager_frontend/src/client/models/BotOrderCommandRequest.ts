/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotOrderAddEquipment } from './BotOrderAddEquipment';
import type { BotOrderAddInstallation } from './BotOrderAddInstallation';
import type { BotOrderAssignCustomer } from './BotOrderAssignCustomer';
import type { BotOrderCreateCustomer } from './BotOrderCreateCustomer';
import type { BotOrderPrepareDocument } from './BotOrderPrepareDocument';
import type { BotOrderRemoveLine } from './BotOrderRemoveLine';
import type { BotOrderSelectProposal } from './BotOrderSelectProposal';
import type { BotOrderSetDetails } from './BotOrderSetDetails';
import type { BotOrderSetSchedule } from './BotOrderSetSchedule';
import type { BotOrderTransition } from './BotOrderTransition';
import type { BotOrderUpdateLine } from './BotOrderUpdateLine';
export type BotOrderCommandRequest = {
    telegram_id: number;
    expected_context_version: number;
    expected_revision: string;
    idempotency_key: string;
    change: (BotOrderSetDetails | BotOrderAssignCustomer | BotOrderCreateCustomer | BotOrderSetSchedule | BotOrderTransition | BotOrderSelectProposal | BotOrderUpdateLine | BotOrderRemoveLine | BotOrderAddEquipment | BotOrderAddInstallation | BotOrderPrepareDocument);
};

