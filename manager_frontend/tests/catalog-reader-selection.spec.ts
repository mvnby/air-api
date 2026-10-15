import { defineComponent } from 'vue';
import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useCatalogReaderSelection } from '../src/composables/useCatalogReaderSelection';
import { managerSession } from '../src/services/manager-session';
import { catalogDecisionSelectionStorageKey, loadCatalogDecisionSelection, saveCatalogDecisionSelection } from '../src/services/catalog-decision-selection';

const identity = (tenantId = 1) => ({ username: 'reader', staff_user_id: 3, tenant_id: tenantId, capabilities: ['crm.manage'] }) as any;
let selection: ReturnType<typeof useCatalogReaderSelection>;
let wrapper: ReturnType<typeof mount>;
const start = () => {
  wrapper = mount(defineComponent({ setup() { selection = useCatalogReaderSelection(); return () => null; } }));
};
afterEach(() => { wrapper?.unmount(); managerSession.auth.value = null; vi.restoreAllMocks(); localStorage.clear(); });

describe('shared reader equipment basket', () => {
  it('retains existing choices, toggles new models and resets when the tenant changes', async () => {
    const auth = identity(); managerSession.auth.value = auth;
    const key = catalogDecisionSelectionStorageKey(auth);
    saveCatalogDecisionSelection([{ id: 10, title: 'Из подбора' }], key);
    start();
    selection.toggle({ id: 11, title: 'Из карточки' });
    expect(loadCatalogDecisionSelection(key).map(item => item.id)).toEqual([10, 11]);
    selection.toggle({ id: 11, title: 'Из карточки' });
    expect(loadCatalogDecisionSelection(key).map(item => item.id)).toEqual([10]);
    managerSession.auth.value = identity(2); await wrapper.vm.$nextTick();
    expect(selection.items.value).toEqual([]);
    expect(loadCatalogDecisionSelection(key)).toHaveLength(1);
    selection.toggle({ id: 20, title: 'Другой кабинет' });
    expect(loadCatalogDecisionSelection(catalogDecisionSelectionStorageKey(identity(2)))).toHaveLength(1);
  });

  it('preserves the 24-model limit and works in memory when local storage is unavailable', () => {
    managerSession.auth.value = identity();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    start();
    for (let id = 1; id <= 24; id++) selection.toggle({ id, title: `Модель ${id}` });
    selection.toggle({ id: 25, title: 'Лишняя' });
    expect(selection.items.value).toHaveLength(24);
    expect(selection.error.value).toContain('24');
    selection.toggle({ id: 1, title: 'Модель 1' });
    expect(selection.items.value).toHaveLength(23);
    expect(selection.error.value).toBe('');
  });
});
