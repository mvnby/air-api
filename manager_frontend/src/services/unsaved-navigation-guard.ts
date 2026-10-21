type NavigationGuard = () => boolean | Promise<boolean>;

const guards = new Set<NavigationGuard>();
let navigationPending = false;
const approvedUnloadEvents = new WeakSet<BeforeUnloadEvent>();
let pendingUnloadApproval: ((event: BeforeUnloadEvent) => void) | null = null;

export const registerUnsavedNavigationGuard = (guard: NavigationGuard) => {
  guards.add(guard);
  return () => { guards.delete(guard); };
};

export const canNavigateAway = async (): Promise<boolean> => {
  // Resolve an inner editor first, then its page; closing it must retain the page guard.
  for (const guard of [...guards].reverse()) {
    if (guards.has(guard) && !await guard()) return false;
  }
  return true;
};

export const runGuardedNavigation = async (
  accept: () => void,
  reject?: () => void,
): Promise<boolean> => {
  if (navigationPending) {
    reject?.();
    return false;
  }
  navigationPending = true;
  try {
    if (!await canNavigateAway()) {
      reject?.();
      return false;
    }
    accept();
    return true;
  } finally {
    navigationPending = false;
  }
};

export const isApprovedUnloadEvent = (event: BeforeUnloadEvent) => {
  if (event.type !== 'beforeunload') return false;
  if (!approvedUnloadEvents.has(event)) pendingUnloadApproval?.(event);
  return approvedUnloadEvents.has(event);
};

// Native Window unload listeners can run before a later capture listener. The first check or
// the one-shot listener claims the approved event; unrelated unload handlers remain active.
export const runGuardedUnload = (unload: () => void) => runGuardedNavigation(() => {
  const approve = (event: BeforeUnloadEvent) => {
    approvedUnloadEvents.add(event);
    if (pendingUnloadApproval === approve) pendingUnloadApproval = null;
    window.removeEventListener('beforeunload', approve, true);
  };
  if (pendingUnloadApproval) window.removeEventListener('beforeunload', pendingUnloadApproval, true);
  pendingUnloadApproval = approve;
  window.addEventListener('beforeunload', approve, { capture: true, once: true });
  try {
    unload();
  } catch (error) {
    if (pendingUnloadApproval === approve) pendingUnloadApproval = null;
    window.removeEventListener('beforeunload', approve, true);
    throw error;
  }
});
