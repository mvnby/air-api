import { inject, provide, type InjectionKey } from 'vue';
import type { PlatformSettingsController } from './usePlatformSettings';
export const PLATFORM_SETTINGS_CONTEXT: InjectionKey<PlatformSettingsController> = Symbol('PlatformSettings');
export const providePlatformSettingsContext = (controller: PlatformSettingsController) => provide(PLATFORM_SETTINGS_CONTEXT, controller);
export const usePlatformSettingsContext = () => {
    const context = inject(PLATFORM_SETTINGS_CONTEXT);
    if (!context) throw new Error('Platform settings context is unavailable');
    return context;
};
