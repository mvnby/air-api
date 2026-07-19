export const parseProductArea = (product: { specs?: Record<string, unknown> } | null | undefined): number => {
  const raw = product?.specs?.area_m2;
  if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) return raw;
  const matches = String(raw ?? "").replace(",", ".").match(/\d+(?:\.\d+)?/g);
  if (!matches?.length) return 0;
  return Math.max(...matches.map(Number).filter((value) => Number.isFinite(value) && value > 0), 0);
};
