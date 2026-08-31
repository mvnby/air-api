export type TransportTerms = {
  car_model: string | null;
  car_number: string | null;
  driver_name: string | null;
  carrier: string | null;
};

export const createDefaultTransportTerms = (): TransportTerms => ({
  car_model: null,
  car_number: null,
  driver_name: null,
  carrier: null,
});

export const serializeTransportTerms = (terms: TransportTerms): TransportTerms => ({
  car_model: terms.car_model?.trim() || null,
  car_number: terms.car_number?.trim() || null,
  driver_name: terms.driver_name?.trim() || null,
  carrier: terms.carrier?.trim() || null,
});

