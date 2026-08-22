/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Monthly stage events, not a cohort funnel.
 *
 * Measurements require a recorded measurement_result and use measurement_date;
 * proposals use proposal_sent_at; sales use closed_at on closed/won orders;
 * installations use completed stages named "Монтаж" and the timestamp policy
 * documented by the KPI.
 * Cycle time is measured from Order.created_at to the stage event.
 */
export type DashboardFunnelStage = {
    stage: 'visitors' | 'leads' | 'measurements' | 'proposals' | 'sales' | 'installations';
    label: string;
    current?: (number | null);
    previous?: (number | null);
    conversion_from_previous_pct?: (number | null);
    /**
     * Average days from Order.created_at to this stage event.
     */
    avg_cycle_days?: (number | null);
};

