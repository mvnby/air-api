type NavigationGuard = () => boolean | Promise<boolean>;

let activeGuard: NavigationGuard | null = null;
let navigationPending = false;

export const registerUnsavedNavigationGuard = (guard: NavigationGuard) => {
  activeGuard = guard;
  return () => { if (activeGuard === guard) activeGuard = null; };
};

export const canNavigateAway = async (): Promise<boolean> => !activeGuard || await activeGuard();

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
