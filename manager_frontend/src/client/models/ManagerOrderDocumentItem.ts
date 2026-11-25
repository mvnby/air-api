/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderDocumentExternalFile } from './ManagerOrderDocumentExternalFile';
export type ManagerOrderDocumentItem = {
    id: number;
    proposal_id?: (number | null);
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    scope_customer_branch_id?: (number | null);
    scope_title?: (string | null);
    scope_address?: (string | null);
    scope_meta?: Record<string, any>;
    base_document_type?: (string | null);
    base_document_type_label?: (string | null);
    base_document_number?: (string | null);
    base_document_date?: (string | null);
    doc_type: string;
    number: string;
    date: string;
    edit_url?: (string | null);
    is_downloadable?: boolean;
    origin?: 'legacy' | 'native_generated' | 'external_upload';
    external_status?: ('received' | 'signed' | null);
    status?: (string | null);
    file_version?: number;
    external_files?: Array<ManagerOrderDocumentExternalFile>;
};

