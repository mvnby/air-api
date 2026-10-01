import type { ServiceLine } from './order-editor-types';

/** Keep the accepted calculation separate from manager-owned commercial lines. */
export const manualInstallationLines = (
  lines: ServiceLine[], index: number, displayIndex = 0,
): { lines: ServiceLine[]; index: number } => {
  const selected = lines[index];
  const revision = selected?.installation_estimate_revision_id;
  if (!revision) return { lines, index };
  let target = index;
  const result = lines.flatMap((line, sourceIndex) => {
    if (line.installation_estimate_revision_id !== revision) return [line];
    // Accepted calculations have no manual costs. Keep an exceptional aggregate
    // with costs intact instead of inventing a cost allocation between groups.
    const groups = line.installation_display_lines?.length && !line.cost
      ? line.installation_display_lines : [line];
    if (sourceIndex < index) target += groups.length - 1;
    if (sourceIndex === index) target += Math.min(displayIndex, groups.length - 1);
    return groups.map((group): ServiceLine => ({
      service_id: line.service_id ?? null,
      title: group.title,
      description: group.description ?? null,
      quantity: group.quantity,
      price: group.price,
      cost: Number(line.cost || 0),
    }));
  });
  return { lines: result, index: target };
};
