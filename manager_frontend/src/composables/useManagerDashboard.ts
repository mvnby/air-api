import { onBeforeUnmount, onMounted, watch } from 'vue';
import { inboxChangedEvent } from '../services/lead-inbox';
import { dashboardContextKey, dashboardOperationsState, dashboardOverviewState, managerLeadsCounterState, managerTaskRemindersState } from '../services/manager-dashboard-state';

export const useManagerDashboard = () => {
  let mounted = false;
  let timer: ReturnType<typeof window.setInterval> | null = null;
  const canRefresh = () => mounted && document.visibilityState !== 'hidden' && Boolean(dashboardContextKey.value);
  const refresh = (counterFreshWithinMs = 0, changed = false) => {
    if (!canRefresh()) return;
    const followUp = changed ? canRefresh : undefined;
    void dashboardOverviewState.refresh(0, followUp);
    void dashboardOperationsState.refresh(0, followUp);
    void managerLeadsCounterState.refresh(counterFreshWithinMs, followUp);
    void managerTaskRemindersState.refresh(counterFreshWithinMs, followUp);
  };
  const resume = () => refresh(5_000);
  const changed = () => refresh(0, true);
  const visibilityChanged = () => {
    if (timer) window.clearInterval(timer);
    timer = null;
    if (document.visibilityState === 'hidden') return;
    resume();
    timer = window.setInterval(resume, 45_000);
  };
  watch(dashboardContextKey, resume, { flush: 'post' });
  onMounted(() => {
    mounted = true;
    window.addEventListener('focus', resume);
    window.addEventListener(inboxChangedEvent, changed);
    document.addEventListener('visibilitychange', visibilityChanged);
    visibilityChanged();
  });
  onBeforeUnmount(() => {
    mounted = false;
    if (timer) window.clearInterval(timer);
    window.removeEventListener('focus', resume);
    window.removeEventListener(inboxChangedEvent, changed);
    document.removeEventListener('visibilitychange', visibilityChanged);
  });
  return { overview: dashboardOverviewState, operations: dashboardOperationsState, leads: managerLeadsCounterState, reminders: managerTaskRemindersState, refresh };
};
