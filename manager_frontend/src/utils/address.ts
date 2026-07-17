import type { AddressSuggestionItem } from '../client';

export const ADDRESS_SUGGEST_DEBOUNCE_MS = 800;
export const ADDRESS_SUGGEST_MIN_SIGNIFICANT_CHARS = 3;

export type AddressCoordinates = {
  latitude: number;
  longitude: number;
};
export type NormalizedAddressSuggestion = AddressSuggestionItem & {
  coordinates?: AddressCoordinates | null;
  components?: Record<string, string> | null;
};

export const normalizeAddressQuery = (value: string) => value.trim().replace(/\s+/g, ' ');

export const hasEnoughAddressCharacters = (value: string) => (
  normalizeAddressQuery(value).replace(/\s/g, '').length >= ADDRESS_SUGGEST_MIN_SIGNIFICANT_CHARS
);

export const buildYandexMapUrl = (
  address: string,
  coordinates?: AddressCoordinates | null,
) => {
  if (coordinates && Number.isFinite(coordinates.latitude) && Number.isFinite(coordinates.longitude)) {
    return `https://yandex.by/maps/?ll=${coordinates.longitude},${coordinates.latitude}&z=17`;
  }
  const normalizedAddress = normalizeAddressQuery(address);
  return normalizedAddress ? `https://yandex.by/maps/?text=${encodeURIComponent(normalizedAddress)}` : '';
};
