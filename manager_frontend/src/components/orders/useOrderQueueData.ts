import { ref } from 'vue';
import type { ManagerOrderBoardPage } from '../../client';
import { orderBoardApi, type BoardQuery } from '../../services/order-board';
import { requireManagerSessionRecovery } from '../../services/manager-session';
import { getApiErrorMessage } from '../../utils/api-errors';

export const useOrderQueueData = () => {
  const pages = ref<Record<string, ManagerOrderBoardPage>>({});
  const busy = ref<Record<string, boolean>>({});
  const errors = ref<Record<string, string>>({});
  const accessError = ref<{ message: string } | null>(null);
  const query = ref<BoardQuery>({ segment: 'b2c', queue: 'active' });
  const phases = ref<Record<string, string>>({});
  let generation = 0;
  const revisions: Record<string, number> = {};
  const reset = () => { generation++; pages.value = {}; errors.value = {}; busy.value = {}; };
  const fetchPage = async (key: string, params: BoardQuery, append: boolean, version = generation) => {
    if (busy.value[key]) return;
    const revision = revisions[key] = (revisions[key] || 0) + 1;
    busy.value[key] = true;
    errors.value[key] = '';
    try {
      const result = await orderBoardApi.page(params);
      if (version !== generation || revisions[key] !== revision) return;
      const previous = pages.value[key];
      pages.value[key] = append && previous ? {
        ...result,
        items: [...(previous.items || []), ...(result.items || [])].filter((item, index, all) => all.findIndex(other => other.id === item.id) === index),
        groups: [...(previous.groups || []), ...(result.groups || [])].filter((item, index, all) => all.findIndex(other => other.key === item.key) === index),
      } : result;
      return result;
    } catch (error) {
      if (version !== generation || revisions[key] !== revision) return;
      const status = (error as { status?: number })?.status;
      if (status === 401 || status === 403) {
        reset();
        if (status === 401) requireManagerSessionRecovery();
        else accessError.value = { message: getApiErrorMessage(error) };
      } else errors.value[key] = getApiErrorMessage(error);
      throw error;
    } finally {
      if (version === generation && revisions[key] === revision) busy.value[key] = false;
    }
  };
  const load = async (params: BoardQuery, columns: string[]) => {
    reset(); query.value = { ...params };
    const version = generation;
    const results = await Promise.allSettled(columns.map(column => fetchPage(column, { ...params, column: column || undefined, phase: phases.value[column] || undefined, page: 1, limit: 25 }, false, version)));
    const forbidden = results.find(result => result.status === 'rejected' && [401, 403].includes(result.reason?.status));
    if (forbidden?.status === 'rejected') throw forbidden.reason;
    return results.map(result => result.status === 'fulfilled' ? result.value : undefined);
  };
  const more = async (column: string, groupKey?: string) => {
    const key = groupKey ? `${column}/${groupKey}` : column;
    const previous = pages.value[key];
    if (previous && !previous.has_more || busy.value[key]) return;
    try {
      await fetchPage(key, { ...query.value, column: column || undefined, phase: phases.value[column] || undefined, group_key: groupKey,
        page: (previous?.page || 0) + 1, limit: 25 }, Boolean(previous));
    } catch { /* The failed page remains retryable without losing earlier pages. */ }
  };
  const setPhase = async (column: string, phase: string) => {
    phases.value[column] = phase;
    for (const key of Array.from(new Set([...Object.keys(pages.value), ...Object.keys(busy.value)])).filter(key => key === column || key.startsWith(`${column}/`))) {
      revisions[key] = (revisions[key] || 0) + 1;
      delete pages.value[key]; delete errors.value[key]; delete busy.value[key];
    }
    try { await fetchPage(column, { ...query.value, column, phase: phase || undefined, page: 1, limit: 25 }, false); }
    catch { /* Column error is visible and retryable. */ }
  };
  return { pages, busy, errors, phases, accessError, query, reset, load, more, setPhase };
};
