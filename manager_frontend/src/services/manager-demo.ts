import { computed } from 'vue';

import { managerSession } from './manager-session';

export const useDemoReadOnly = () => computed(() => Boolean(
  managerSession.auth.value?.demo_read_only,
));

export const DEMO_READ_ONLY_MESSAGE = 'Демонстрационный режим: изменения не сохраняются';
