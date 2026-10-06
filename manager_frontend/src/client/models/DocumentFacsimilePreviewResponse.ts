/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FacsimilePlacement } from './FacsimilePlacement';
import type { FacsimilePreviewAsset } from './FacsimilePreviewAsset';
import type { FacsimilePreviewPage } from './FacsimilePreviewPage';
export type DocumentFacsimilePreviewResponse = {
    document_id: number;
    source_checksum_sha256: string;
    signed_artifact_id: (string | null);
    can_save: boolean;
    pages: Array<FacsimilePreviewPage>;
    signature: FacsimilePreviewAsset;
    seal: FacsimilePreviewAsset;
    placement: FacsimilePlacement;
};

