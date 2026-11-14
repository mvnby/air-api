import { defineAsyncComponent, defineComponent, h, type Component } from 'vue';
import ManagerModuleRecovery from '../components/manager/ManagerModuleRecovery.vue';
import type { ManagerModule, ModuleCategory } from './manager-module-recovery';
import { loadManagerModule } from './manager-module-loader';
export { MANAGER_MODULE_TIMEOUT_MS } from './manager-module-loader';

// Keep imports lazy and fail once: retries against the old module graph cannot repair it.
export const defineManagerAsyncComponent = <T extends Component>(
  module: ManagerModule,
  loader: () => Promise<T | { default: T }>,
  category: ModuleCategory = 'route',
) => defineAsyncComponent<T>({
  loader: () => loadManagerModule(module, loader, category),
  delay: 0,
  loadingComponent: defineComponent({ render: () => h(ManagerModuleRecovery, { loading: true }) }),
  errorComponent: defineComponent({
    inheritAttrs: false,
    render: () => h(ManagerModuleRecovery, { module, category }),
  }),
  onError(_error, _retry, fail) { fail(); },
});
