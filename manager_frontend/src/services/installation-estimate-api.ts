import { ManagerInstallationEstimatesService, type InstallationResolvePayload, type InstallationResolveResponse, type ManagerInstallationStandardTariff } from '../client';

export const resolveInstallationStandard = (body: InstallationResolvePayload) =>
  ManagerInstallationEstimatesService.resolveManagerInstallationTariff(body);

export type StandardInstallationChoice = ManagerInstallationStandardTariff & { bookRevision?: number | null };
export const listInstallationStandardTariffs = async () => {
  const response = await ManagerInstallationEstimatesService.listManagerInstallationStandardTariffs();
  return { ...response, items: (response.items ?? []).map((tariff) => ({
    ...tariff, bookRevision: response.price_book_revision,
  })) };
};

/** The standard allowance is the main wall passage up to 80 cm; thin passages are extras. */
export const installationStandardWork = (tariff: InstallationResolveResponse) => {
  const included = tariff.included || {};
  const holes = included.holes_by_type || {};
  const route = Number(included.route_m);
  const quantity = (code: string) => Number(holes[code] ?? 0);
  const thin = quantity('through_thin');
  const thick = quantity('through_thick') + quantity('shared_pass_through');
  const over80 = quantity('through_over_80');
  const unsupported = Object.keys(holes).some((code) =>
    !['through_thin', 'through_thick', 'through_over_80', 'shared_pass_through'].includes(code) && Number(holes[code]) > 0);
  if (!['fixed', 'from'].includes(tariff.status) || included.route_m == null ||
      !Number.isFinite(route) || route < 0 || route > 1000 || unsupported ||
      [thin, thick, over80].some((value) => !Number.isInteger(value) || value < 0 || value > 100)) {
    throw new Error('Для этого оборудования стандартный состав недоступен. Настройте монтаж вручную.');
  }
  return { route, thin, thick, over80 };
};
