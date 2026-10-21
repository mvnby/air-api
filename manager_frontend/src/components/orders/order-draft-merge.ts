// Draft recovery is a three-way merge. Missing values also represent row deletion.
export type DraftConflict = { id: string; path: string[]; base: unknown; local: unknown; server: unknown; legacy: boolean };
export type DraftChoices = Record<string, { choice: 'local' | 'server'; server: unknown }>;
export const equalDraftValue = (a: unknown, b: unknown): boolean => {
  if (Object.is(a, b)) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((value, i) => equalDraftValue(value, b[i]));
  if (isRecord(a) && isRecord(b)) {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    return [...keys].every(key => equalDraftValue(a[key], b[key]));
  }
  return false;
};
export const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export function mergeOrderDraft(base: unknown, local: unknown, server: unknown, choices: DraftChoices = {}, legacy = false) {
  const conflicts: DraftConflict[] = [];
  const visit = (before: unknown, mine: unknown, fresh: unknown, path: string[]): unknown => {
    if (equalDraftValue(mine, fresh)) return fresh;
    if (!legacy && equalDraftValue(before, mine)) return fresh;
    if (!legacy && equalDraftValue(before, fresh)) return mine;
    if (path.join('.') !== 'form.currency' && isRecord(mine) && isRecord(fresh) && (isRecord(before) || legacy)) {
      const original = isRecord(before) ? before : {};
      // In legacy drafts a missing field is unknown, not a request to delete it.
      const keys = legacy ? Object.keys(mine) : [...new Set([...Object.keys(original), ...Object.keys(mine), ...Object.keys(fresh)])];
      const result = { ...fresh };
      const currencyKeys = ['enableCurrency', 'targetCurrency', 'targetCurrencyAmount'];
      const currency = !legacy && path.join('.') === 'form' && keys.some(key => currencyKeys.includes(key));
      if (currency) {
        const values = (source: Record<string, unknown>) => Object.fromEntries(currencyKeys.map(key => [key, source[key]]));
        Object.assign(result, visit(values(original), values(mine), values(fresh), [...path, 'currency']));
      }
      for (const key of keys) {
        if (currency && currencyKeys.includes(key)) continue;
        result[key] = visit(original[key], mine[key], fresh[key], [...path, key]);
      }
      return result;
    }
    if (!legacy && path.length === 1 && ['products', 'services'].includes(path[0]!) && Array.isArray(before) && Array.isArray(mine) && Array.isArray(fresh)) {
      const rowId = (row: unknown) => isRecord(row) && typeof row.link_id === 'number' && row.link_id > 0 ? String(row.link_id) : null;
      // New local rows have no server identity yet; preserve concurrent server additions.
      const byId = (rows: unknown[]) => new Map(rows.flatMap(row => rowId(row) ? [[rowId(row)!, row] as const] : []));
      const originals = byId(before), locals = byId(mine), servers = byId(fresh);
      const additions = mine.filter(row => !rowId(row));
      // Without a client-generated row ID, concurrent additions can be a lost ACK,
      // including a row another manager has already renamed/repriced. Require review.
      const possibleAcknowledgements = additions.length ? [...servers].filter(([id]) => !originals.has(id)) : [];
      const ambiguousIds = new Set(possibleAcknowledgements.map(([id]) => id));
      const ambiguousLocal = possibleAcknowledgements.length ? additions : [];
      const ids = [...new Set([...servers.keys(), ...originals.keys(), ...locals.keys()])].filter(id => !ambiguousIds.has(id));
      const result = ids.map(id => visit(originals.get(id), locals.get(id), servers.get(id), [...path, id])).filter(row => row !== undefined);
      const reviewedAdditions = ambiguousLocal.length ? visit(undefined, ambiguousLocal, possibleAcknowledgements.map(([, row]) => row), [...path, 'additions']) as unknown[] : [];
      return [...result, ...reviewedAdditions, ...additions.filter(row => !ambiguousLocal.includes(row))];
    }
    const id = JSON.stringify(path);
    if (choices[id] && equalDraftValue(choices[id].server, fresh)) return choices[id].choice === 'local' ? mine : fresh;
    conflicts.push({ id, path, base: before, local: mine, server: fresh, legacy });
    return fresh;
  };
  const value = visit(base, local, server, []) as Record<string, unknown>;
  const restoredRows = new Map<object, number>();
  for (const kind of ['products', 'services']) {
    if (!Array.isArray(value[kind]) || !isRecord(server) || !Array.isArray(server[kind])) continue;
    const existing = new Set(server[kind].filter(isRecord).map(row => row.link_id));
    value[kind] = value[kind].map((row: unknown) => {
      if (!isRecord(row) || typeof row.link_id !== 'number' || existing.has(row.link_id)) return row;
      // A resolved server deletion creates a new line, never a reference to the deleted record.
      const detached = {
        ...row, link_id: null,
        ...(kind === 'services' ? { installation_estimate_revision_id: null, installation_line_index: null, installation_projection_mode: null, installation_display_lines: undefined } : {}),
      };
      restoredRows.set(detached, row.link_id);
      return detached;
    });
  }
  return { value, conflicts, restoredRows };
}
