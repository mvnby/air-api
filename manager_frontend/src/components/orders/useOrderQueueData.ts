import { ref } from 'vue';
import type { ManagerOrderBoardPage } from '../../client';
import { orderBoardApi, type BoardQuery } from '../../services/order-board';
import { requireManagerSessionRecovery } from '../../services/manager-session';
import { getApiErrorMessage } from '../../utils/api-errors';

const mergePages = (previous: ManagerOrderBoardPage, next: ManagerOrderBoardPage): ManagerOrderBoardPage => ({
  ...next,
  items: [...(previous.items || []), ...(next.items || [])].filter((item, index, all) => all.findIndex(other => other.id === item.id) === index),
  groups: [...(previous.groups || []), ...(next.groups || [])].filter((item, index, all) => all.findIndex(other => other.key === item.key) === index),
});
export const useOrderQueueData = () => {
  const pages = ref<Record<string, ManagerOrderBoardPage>>({});
  const busy = ref<Record<string, boolean>>({}), errors = ref<Record<string, string>>({});
  const accessError = ref<{ message: string } | null>(null);
  const query = ref<BoardQuery>({ segment: 'b2c', queue: 'active' });
  const phases = ref<Record<string, string>>({});
  const refreshing = ref(false), stale = ref(false);
  let generation = 0, refreshTicket = 0;
  let refreshPromise: Promise<boolean> | null = null;
  let rootColumns: string[] = [];
  const revisions: Record<string, number> = {};
  const reset = () => { generation++; refreshTicket++; refreshPromise = null; refreshing.value = false; stale.value = false; accessError.value = null; pages.value = {}; errors.value = {}; busy.value = {}; };
  const forbidden = (error: unknown) => {
    const status = (error as { status?: number })?.status;
    if (status !== 401 && status !== 403) return false;
    reset();
    if (status === 401) requireManagerSessionRecovery();
    else accessError.value = { message: getApiErrorMessage(error) };
    return true;
  };
  const paramsFor = (key: string, page: number): BoardQuery => {
    const slash = key.indexOf('/'), column = slash < 0 ? key : key.slice(0, slash);
    return { ...query.value, column: column || undefined, phase: phases.value[column] || undefined,
      group_key: slash < 0 ? undefined : key.slice(slash + 1), page, limit: 25 };
  };
  const fetchPage = async (key: string, params: BoardQuery, append: boolean, version = generation) => {
    if (busy.value[key]) return;
    const revision = revisions[key] = (revisions[key] || 0) + 1;
    busy.value[key] = true; errors.value[key] = '';
    try {
      const result = await orderBoardApi.page(params);
      if (version !== generation || revisions[key] !== revision) return;
      pages.value[key] = append && pages.value[key] ? mergePages(pages.value[key], result) : result;
      return result;
    } catch (error) {
      if (version !== generation || revisions[key] !== revision) return;
      if (!forbidden(error)) errors.value[key] = getApiErrorMessage(error);
      throw error;
    } finally { if (version === generation && revisions[key] === revision) busy.value[key] = false; }
  };
  const load = async (params: BoardQuery, columns: string[]) => {
    reset(); query.value = { ...params }; rootColumns = [...columns];
    const version = generation;
    const results = await Promise.allSettled(columns.map(column => fetchPage(column, paramsFor(column, 1), false, version)));
    const denied = results.find(result => result.status === 'rejected' && [401, 403].includes(result.reason?.status));
    if (denied?.status === 'rejected') throw denied.reason;
    return results.map(result => result.status === 'fulfilled' ? result.value : undefined);
  };
  const more = async (column: string, groupKey?: string) => {
    if (refreshing.value) return;
    const key = groupKey ? `${column}/${groupKey}` : column, previous = pages.value[key];
    if (previous && !previous.has_more || busy.value[key]) return;
    try { await fetchPage(key, paramsFor(key, (previous?.page || 0) + 1), Boolean(previous)); }
    catch { /* A failed read retains the earlier bounded pages and stays retryable. */ }
  };
  const setPhase = async (column: string, phase: string) => {
    // An in-flight full revalidation belongs to the previous filters.
    refreshTicket++;
    phases.value[column] = phase;
    for (const key of Array.from(new Set([...Object.keys(pages.value), ...Object.keys(busy.value)])).filter(key => key === column || key.startsWith(`${column}/`))) {
      revisions[key] = (revisions[key] || 0) + 1;
      delete pages.value[key]; delete errors.value[key]; delete busy.value[key];
    }
    try { await fetchPage(column, paramsFor(column, 1), false); }
    catch { /* Column errors remain independent and retryable. */ }
  };
  const refreshLoaded = (): Promise<boolean> => {
    refreshTicket++;
    if (refreshPromise) return refreshPromise;
    const version = generation;
    const run = async () => {
      refreshing.value = true;
      try {
        while (version === generation) {
          const ticket = refreshTicket;
          const bounds = Object.fromEntries([...rootColumns, ...Object.keys(pages.value)].map(key => [key, pages.value[key]?.page || 1]));
          for (const key of Object.keys(busy.value)) { revisions[key] = (revisions[key] || 0) + 1; busy.value[key] = false; }
          const next = { ...pages.value }, nextErrors: Record<string, string> = {};
          const entries = Object.entries(bounds);
          for (let offset = 0; offset < entries.length; offset += 4) {
            await Promise.all(entries.slice(offset, offset + 4).map(async ([key, count]) => {
              try {
                let merged: ManagerOrderBoardPage | undefined;
                for (let page = 1; page <= count; page++) {
                  if (version !== generation || ticket !== refreshTicket) return;
                  const result = await orderBoardApi.page(paramsFor(key, page));
                  merged = merged ? mergePages(merged, result) : result;
                  if (!result.has_more) break;
                }
                if (merged) next[key] = merged;
              } catch (error) {
                if (version !== generation || ticket !== refreshTicket) return;
                if (!forbidden(error)) nextErrors[key] = getApiErrorMessage(error);
              }
            }));
            if (version !== generation || ticket !== refreshTicket) break;
          }
          if (version !== generation) return false;
          if (ticket !== refreshTicket) continue; // A later saved command requires a newer read snapshot.
          for (const key of Object.keys(next)) {
            const slash = key.indexOf('/');
            if (slash >= 0 && !nextErrors[key.slice(0, slash)] && !next[key.slice(0, slash)]?.groups?.some(group => group.key === key.slice(slash + 1) && group.count > 1)) delete next[key];
          }
          stale.value = Object.keys(nextErrors).length > 0;
          if (!stale.value) pages.value = next;
          errors.value = nextErrors;
          return !stale.value;
        }
        return false;
      } finally { if (version === generation) refreshing.value = false; }
    };
    const promise = run(); refreshPromise = promise;
    void promise.finally(() => { if (refreshPromise === promise) refreshPromise = null; });
    return promise;
  };
  return { pages, busy, errors, phases, accessError, query, reset, load, more, setPhase, refreshLoaded, refreshing, stale };
};
