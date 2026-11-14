import { recordModuleFailure, type ManagerModule, type ModuleCategory } from './manager-module-recovery';

export const MANAGER_MODULE_TIMEOUT_MS = 20_000;
class ModuleLoadFailure extends Error {
  readonly code: 'import-failed' | 'timeout';
  constructor(code: 'import-failed' | 'timeout') { super(code); this.code = code; }
}

// A deadline ends this attempt; a late import cannot replace the recovery UI.
export const loadManagerModule = <T>(module: ManagerModule, loader: () => Promise<T>, category: ModuleCategory): Promise<T> =>
  new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new ModuleLoadFailure('timeout')), MANAGER_MODULE_TIMEOUT_MS);
    try {
      loader().then(resolve, () => reject(new ModuleLoadFailure('import-failed')))
        .finally(() => window.clearTimeout(timer));
    } catch {
      window.clearTimeout(timer);
      reject(new ModuleLoadFailure('import-failed'));
    }
  }).catch(error => {
    recordModuleFailure(module, category, error instanceof ModuleLoadFailure ? error.code : 'import-failed');
    throw error;
  });
