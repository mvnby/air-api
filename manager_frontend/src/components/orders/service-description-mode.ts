import { ref } from 'vue';
import type { ManagerQuickTariffResponse } from '../../client';

export type ServiceDescriptionMode = 'short' | 'full';

export type ServiceDescriptionLine = {
  service_id?: number | null;
  title: string;
  quantity: number;
  price: number;
  cost: number;
  tariff_id?: number | null;
  template_short_name?: string | null;
  template_full_description?: string | null;
  template_applied_text?: string | null;
  description_mode?: ServiceDescriptionMode;
};

const STORAGE_KEY = 'manager.service-description-mode';

export const readServiceDescriptionMode = (): ServiceDescriptionMode => {
  if (typeof window === 'undefined') return 'short';
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'full' ? 'full' : 'short';
  } catch {
    return 'short';
  }
};

export const writeServiceDescriptionMode = (mode: ServiceDescriptionMode) => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // The choice is only a convenience; restricted storage must not block editing.
  }
};

export const resolveServiceDescription = (
  shortName: string,
  fullDescription: string | null | undefined,
  mode: ServiceDescriptionMode,
) => {
  const shortText = String(shortName || '').trim();
  if (mode === 'full') return String(fullDescription || '').trim() || shortText;
  return shortText;
};

export const canReplaceServiceDescription = (
  current: string,
  lastApplied: string | null | undefined,
  shortName: string,
  fullDescription: string | null | undefined,
) => {
  const normalized = String(current || '').trim();
  if (!normalized) return true;
  return [lastApplied, shortName, fullDescription]
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .includes(normalized);
};

export const useServiceDescriptionMode = () => {
  const preferredMode = ref<ServiceDescriptionMode>(readServiceDescriptionMode());

  const rememberMode = (mode: ServiceDescriptionMode) => {
    preferredMode.value = mode;
    writeServiceDescriptionMode(mode);
  };

  const applyTariffTemplate = (
    row: ServiceDescriptionLine,
    option: ManagerQuickTariffResponse,
    requestedMode: ServiceDescriptionMode = preferredMode.value,
  ) => {
    const shortName = option.short_name || option.title || 'Услуга';
    const fullDescription = String(option.full_description || '').trim() || null;
    const mode: ServiceDescriptionMode = requestedMode === 'full' && fullDescription ? 'full' : 'short';
    const title = resolveServiceDescription(shortName, fullDescription, mode);
    Object.assign(row, {
      service_id: null,
      tariff_id: option.tariff_id,
      template_short_name: shortName,
      template_full_description: fullDescription,
      template_applied_text: title,
      description_mode: mode,
      title,
      quantity: Math.max(1, Number(row.quantity || 1)),
      price: Math.round(Number(option.price || 0)),
      cost: 0,
    });
  };

  const replaceLineDescription = (
    row: ServiceDescriptionLine,
    mode: ServiceDescriptionMode,
    confirmReplacement: () => boolean,
  ) => {
    if (!row.template_short_name) return false;
    const nextTitle = resolveServiceDescription(
      row.template_short_name,
      row.template_full_description,
      mode,
    );
    if (!nextTitle) return false;
    if (
      nextTitle !== row.title
      && !canReplaceServiceDescription(
        row.title,
        row.template_applied_text,
        row.template_short_name,
        row.template_full_description,
      )
      && !confirmReplacement()
    ) {
      return false;
    }
    row.title = nextTitle;
    row.template_applied_text = nextTitle;
    row.description_mode = mode;
    rememberMode(mode);
    return true;
  };

  return { preferredMode, rememberMode, applyTariffTemplate, replaceLineDescription };
};
