/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerProductCollectionItemPayload } from './ManagerProductCollectionItemPayload';
import type { ManagerProductCollectionPlacementPayload } from './ManagerProductCollectionPlacementPayload';
import type { ManagerProductCollectionUpdate } from './ManagerProductCollectionUpdate';
export type ManagerProductCollectionWorkspacePayload = {
    collection: ManagerProductCollectionUpdate;
    items: Array<ManagerProductCollectionItemPayload>;
    placements: Array<ManagerProductCollectionPlacementPayload>;
};

