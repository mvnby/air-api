type NavigationGuard = () => boolean | Promise<boolean>;

const guards = new Set<NavigationGuard>();
let navigationPending = false;

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
