import { afterEach, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import PersonalOffersView from '../src/views/PersonalOffersView.vue';
import { managerSession } from '../src/services/manager-session';
import { personalOffersApi, type PersonalOffer } from '../src/services/personal-offers';
import { cancelActiveDialog, resetUiFeedbackForTests, setDialogInput, submitActiveDialog, uiDialogState } from '../src/services/ui-feedback';

const expiry = new Date(Date.now() + 86_400_000).toISOString();
const active: PersonalOffer = {
  id: 4, version: 2, order_id: 42, expires_at: expiry, rooms: [],
  published: { url: 'https://example.test/predlozhenie/test/', expires_at: expiry },
};
let wrapper: VueWrapper | undefined;

async function openList(readOnly = false) {
  window.history.replaceState({}, '', '/manager/personal-offers?orderId=42');
  managerSession.auth.value = { demo_read_only: readOnly } as never;
  vi.spyOn(personalOffersApi, 'list').mockResolvedValue({ items: [active], has_more: false });
  wrapper = mount(PersonalOffersView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}

afterEach(() => {
  wrapper?.unmount();
  resetUiFeedbackForTests();
  vi.restoreAllMocks();
  managerSession.auth.value = null;
  window.history.replaceState({}, '', '/');
});

it('creates in the current order scope and renames an existing row without touching its link', async () => {
  const rename = vi.spyOn(personalOffersApi, 'rename').mockResolvedValue({ ...active, version: 3, title: 'Склад — инверторы' });
  const view = await openList();
  expect(personalOffersApi.list).toHaveBeenCalledWith(42, undefined);
  expect(view.get('a[href*="new=1"]').attributes('href')).toBe('/manager/personal-offers?new=1&orderId=42');
  expect(view.get('a[href*="offerId=4"]').attributes('href')).toBe('/manager/personal-offers?orderId=42&offerId=4');
  await view.get('button[aria-label="Переименовать Предложение №4"]').trigger('click');
  expect(uiDialogState.title).toBe('Переименовать предложение');
  setDialogInput('  Склад — инверторы  ');
  await submitActiveDialog();
  await flushPromises();
  expect(rename).toHaveBeenCalledExactlyOnceWith(4, 'Склад — инверторы', 2);
  expect(view.get('a[href*="offerId=4"]').text()).toContain('Склад — инверторы');
  expect(view.text()).toContain('Опубликовано');
});

it('warns about the public link and removes a row only after confirmation', async () => {
  const remove = vi.spyOn(personalOffersApi, 'delete').mockResolvedValue(undefined);
  const view = await openList();
  const action = view.get('button[aria-label="Удалить Предложение №4"]');
  await action.trigger('click');
  expect(uiDialogState.variant).toBe('danger');
  expect(uiDialogState.description).toContain('Клиентская ссылка перестанет открываться.');
  cancelActiveDialog();
  await flushPromises();
  expect(remove).not.toHaveBeenCalled();
  expect(view.find('a[href*="offerId=4"]').exists()).toBe(true);

  await action.trigger('click');
  await submitActiveDialog();
  await flushPromises();
  expect(remove).toHaveBeenCalledExactlyOnceWith(4, 2);
  expect(view.find('a[href*="offerId=4"]').exists()).toBe(false);
  expect(view.text()).toContain('Предложение удалено.');
});

it('keeps existing rows browsable in read-only mode', async () => {
  const view = await openList(true);
  expect(view.find('a[href*="offerId=4"]').exists()).toBe(true);
  expect(view.find('a[href*="new=1"]').exists()).toBe(false);
  expect(view.find('[aria-label^="Удалить"]').exists()).toBe(false);
  expect(view.find('[aria-label^="Переименовать"]').exists()).toBe(false);
});
