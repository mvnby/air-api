/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkerMoneyEntry = {
    id: number;
    kind: 'client_receipt' | 'handover' | 'receipt_reversal' | 'handover_reversal' | 'offset' | 'offset_reversal';
    status: 'recorded' | 'pending' | 'confirmed' | 'rejected' | 'cancelled' | 'reversed';
    amount: string;
    currency: 'BYN' | 'USD' | 'EUR';
    created_at: string;
    order_id?: (number | null);
    title?: (string | null);
    recipient_staff_user_id?: (number | null);
    recipient_name?: (string | null);
    version?: number;
    can_reverse?: boolean;
};

