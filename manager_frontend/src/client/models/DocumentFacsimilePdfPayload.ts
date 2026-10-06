/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FacsimileImagePlacement } from './FacsimileImagePlacement';
export type DocumentFacsimilePdfPayload = {
    signature: FacsimileImagePlacement;
    seal: FacsimileImagePlacement;
    source_checksum_sha256: string;
    expected_signed_artifact_id?: (string | null);
    signature_asset_id: string;
    seal_asset_id: string;
};

