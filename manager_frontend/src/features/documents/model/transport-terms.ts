import type { TransportOperation, TransportTermsPayload } from '../../../client';

export type TransportTerms = TransportTermsPayload;
export type HandlingStage = 'loading' | 'unloading';
export const handlingStages: { key: HandlingStage; label: string }[] = [
  { key: 'loading', label: 'Погрузка' }, { key: 'unloading', label: 'Разгрузка' },
];

export const createDefaultTransportTerms = (): TransportTerms => ({
  car_model: null, car_number: null, driver_name: null, carrier: null,
});

export const serializeTransportTerms = (terms: TransportTerms): TransportTerms => ({
  ...terms,
  car_model: terms.car_model?.trim() || null,
  car_number: terms.car_number?.trim() || null,
  driver_name: terms.driver_name?.trim() || null,
  carrier: terms.carrier?.trim() || null,
});

export function transportTermsError(terms: TransportTerms): string {
  if (terms.freight_payer_unp && !/^[0-9]{9}$/.test(terms.freight_payer_unp)) {
    return 'УНП плательщика должен содержать 9 цифр';
  }
  for (const { key, label } of handlingStages) {
    const op: TransportOperation | null | undefined = terms[key];
    if (op?.arrived_at && op.departed_at && op.departed_at < op.arrived_at) {
      return `${label}: убытие указано раньше прибытия`;
    }
    if (op?.downtime_minutes != null && (!Number.isSafeInteger(op.downtime_minutes) || op.downtime_minutes < 0)) {
      return `${label}: укажите простой в целых минутах`;
    }
  }
  return '';
}
