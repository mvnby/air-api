import { defineComponent, h, ref } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createManagerOrder: vi.fn(),
  getLeadsInbox: vi.fn(),
  getLeadsCounter: vi.fn(),
  getManagerCustomers: vi.fn(),
}));

vi.mock('../src/api', () => ({
  api: {
    createManagerOrder: mocks.createManagerOrder,
    getLeadsInbox: mocks.getLeadsInbox,
    getLeadsCounter: mocks.getLeadsCounter,
    getManagerCustomers: mocks.getManagerCustomers,
    patchManagerOrder: vi.fn(),
  },
}));
vi.mock('../src/composables/useBelarusPhoneMask', () => ({
  useBelarusPhoneMask: (_input: unknown, model: { value: string }) => ({ unmaskedValue: model }),
}));
vi.mock('../src/composables/useB2BLookup', () => ({
  useB2BLookup: () => ({ lookupCompany: vi.fn(), isEgrLoading: { value: false } }),
}));
vi.mock('../src/components/leads/LeadInboxCard.vue', () => ({
  default: { name: 'LeadInboxCard', props: ['item', 'quickIncoming'], emits: ['edit-incoming', 'updated'], template: '<article data-testid="inbox-item">{{ item.customer_name }}<button v-if="quickIncoming" data-testid="edit-incoming" @click="$emit(\'edit-incoming\')">Исправить</button></article>' },
}));
vi.mock('../src/components/leads/QuickIncomingCapture.vue', () => ({
  default: { name: 'QuickIncomingCapture', props: ['leadId'], emits: ['close', 'saved'], template: '<section data-testid="quick-incoming">{{ leadId || \'new\' }}</section>' },
}));
vi.mock('../src/components/leads/LeadQualifyModal.vue', () => ({ default: { template: '<div />' } }));
vi.mock('../src/components/leads/EmailLeadImportPanel.vue', () => ({ default: { template: '<div data-testid="email-import">Импорт почты</div>' } }));
vi.mock('../src/components/ui/AddressSuggestInput.vue', () => ({ default: { template: '<div />' } }));

import LeadInbox from '../src/views/LeadInbox.vue';
import KitlaneShell from '../src/components/kitlane/KitlaneShell.vue';
import ManagerAccountMenu from '../src/components/manager/ManagerAccountMenu.vue';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

const response = (items: Array<Record<string, unknown>>) => ({
  items,
  total: items.length,
  meta: { page: 1, pages: 1, total: items.length },
  source_counts: items.reduce<Record<string, number>>((counts, item) => {
    const source = String(item.source || 'other');
    counts[source] = (counts[source] || 0) + 1;
    return counts;
  }, {}),
});
let shellWrapper: VueWrapper | null = null;
const activeItem = { id: 1, source: 'site', status: 'new_lead', is_new: true, customer_name: 'Анна', phone: '+375291112233', email: 'anna@example.test', comment: 'Нужен монтаж', created_at: '2026-09-01T10:00:00Z' };
const archiveItem = { id: 2, source: 'email', status: 'closed', is_new: false, customer_name: 'Борис', customer_inn: '123456789', comment: 'Закрыто', created_at: '2026-09-01T10:00:00Z' };

describe('LeadInbox usability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    managerSession.auth.value = null;
    managerStorefrontSelection.selectedSlug.value = null;
    mocks.getLeadsCounter.mockResolvedValue({ pending_count: 1, unread_count: 1, count: 1 });
    mocks.getManagerCustomers.mockResolvedValue({ items: [] });
    mocks.getLeadsInbox.mockImplementation((scope: string) => Promise.resolve(response(scope === 'active' ? [activeItem] : [archiveItem])));
  });

  afterEach(() => {
    shellWrapper?.unmount(); shellWrapper = null;
    vi.unstubAllGlobals();
    vi.useRealTimers();
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/manager/leads');
  });

  it('searches on the server and switches scope directly', async () => {
    mocks.getLeadsInbox.mockImplementation((scope: string, _page: number, _limit: number, search?: string) => Promise.resolve(
      response(search ? (search === 'example.test' ? [activeItem] : []) : scope === 'active' ? [activeItem] : [archiveItem]),
    ));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Анна');

    expect(wrapper.find('input[type="search"]').exists()).toBe(false);
    await wrapper.get('button[aria-label="Поиск по входящим обращениям"]').trigger('click');
    await wrapper.get('input[type="search"]').setValue('example.test');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledWith('active', 1, 50, 'example.test', undefined, false, 'deadline');
    expect(wrapper.findAll('[data-testid="inbox-item"]')).toHaveLength(1);
    await wrapper.get('input[type="search"]').setValue('нет совпадений');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(wrapper.text()).toContain('По этому запросу обращений нет');
    await wrapper.get('button[aria-label="Очистить поиск"]').trigger('click');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    await wrapper.get('button[aria-label="Архив"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
  });

  it('requests only one page and restores source, scope and page for the same account and storefront', async () => {
    managerSession.auth.value = { tenant_id: 11, staff_user_id: 7, username: 'manager' } as never;
    managerStorefrontSelection.selectedSlug.value = 'main';
    mocks.getLeadsInbox.mockImplementation((_scope: string, page: number) => Promise.resolve({
      items: page === 1 ? [activeItem] : [archiveItem], total: 61,
      meta: { page, pages: 2, total: 61 },
      source_counts: { belzakupki: 61 },
    }));
    const first = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledTimes(1);
    await first.findAll('.channels button').find(button => button.get('.channel-label').text() === 'Тендеры')!.trigger('click');
    await flushPromises();
    await first.findAll('button').find(button => button.text() === 'Далее')!.trigger('click');
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 2, 50, undefined, 'belzakupki', false, 'deadline');
    first.unmount();

    const returned = mount(LeadInbox);
    await flushPromises();
    expect(returned.findAll('.channels button').find(button => button.get('.channel-label').text() === 'Тендеры')!.attributes('aria-pressed')).toBe('true');
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 2, 50, undefined, 'belzakupki', false, 'deadline');
    returned.unmount();

    managerStorefrontSelection.selectedSlug.value = 'other';
    const other = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
    other.unmount();
  });

  it('retries errors and moves back when the requested page became empty', async () => {
    mocks.getLeadsInbox.mockRejectedValueOnce(new Error('network'));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить');
    await wrapper.get('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Анна');
    wrapper.unmount();

    managerSession.auth.value = { tenant_id: 11, staff_user_id: 7, username: 'manager' } as never;
    managerStorefrontSelection.selectedSlug.value = 'main';
    window.sessionStorage.setItem('mvn_manager_storefront_v1:11:staff-7:main:lead-inbox', JSON.stringify({ scope: 'active', source: '', search: '', page: 2 }));
    mocks.getLeadsInbox.mockImplementation((_scope: string, page: number) => Promise.resolve(page === 2
      ? { items: [], total: 1, meta: { page: 2, pages: 1, total: 1 } }
      : response([activeItem])));
    const restored = mount(LeadInbox);
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenCalledWith('active', 2, 50, undefined, undefined, false, 'deadline');
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
    expect(restored.get('[data-testid="inbox-item"]').text()).toBe('Анна');
    restored.unmount();
  });

  it('does not apply an older response after scope changes', async () => {
    let resolveActive: ((value: ReturnType<typeof response>) => void) | undefined;
    mocks.getLeadsInbox.mockImplementation((scope: string) => scope === 'active'
      ? new Promise((resolve) => { resolveActive = resolve; })
      : Promise.resolve(response([archiveItem])));
    const wrapper = mount(LeadInbox);
    await wrapper.get('button[aria-label="Архив"]').trigger('click');
    await flushPromises();
    resolveActive?.(response([activeItem]));
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
  });

  it('ignores an older search response after a newer query', async () => {
    let resolveOld: ((value: ReturnType<typeof response>) => void) | undefined;
    mocks.getLeadsInbox.mockImplementation((_scope: string, _page: number, _limit: number, search?: string) => {
      if (search === 'old') return new Promise(resolve => { resolveOld = resolve; });
      return Promise.resolve(response(search === 'new' ? [archiveItem] : [activeItem]));
    });
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.get('button[aria-label="Поиск по входящим обращениям"]').trigger('click');
    await wrapper.get('input[type="search"]').setValue('old');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    await wrapper.get('input[type="search"]').setValue('new');
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    resolveOld?.(response([activeItem]));
    await flushPromises();
    expect(wrapper.get('[data-testid="inbox-item"]').text()).toBe('Борис');
    wrapper.unmount();
  });

  it('uses server counts across pages and keeps an empty selected source available', async () => {
    mocks.getLeadsInbox.mockResolvedValue({ ...response([activeItem]), source_counts: { site: 53, email: 2 } });
    const wrapper = mount(LeadInbox);
    await flushPromises();
    const channels = () => wrapper.findAll('.channels button');
    expect(channels().map(button => button.get('.channel-label').text())).toEqual(['Все', 'Сайт', 'Почта']);
    expect(channels().map(button => button.get('.channel-count').text())).toEqual(['55', '53', '2']);

    mocks.getLeadsInbox.mockResolvedValue({ ...response([]), source_counts: { email: 2 } });
    await channels()[1]!.trigger('click');
    await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, 'site', false, 'deadline');
    expect(channels()[1]!.attributes('aria-pressed')).toBe('true');
    expect(channels()[1]!.get('.channel-count').text()).toBe('0');
    await channels()[0]!.trigger('click');
    await flushPromises();
    expect(channels().map(button => button.get('.channel-label').text())).toEqual(['Все', 'Почта']);
    wrapper.unmount();
  });

  it('restores a visible search and clears its filter when collapsed with Escape', async () => {
    managerSession.auth.value = { tenant_id: 11, staff_user_id: 7, username: 'manager' } as never;
    managerStorefrontSelection.selectedSlug.value = 'main';
    window.sessionStorage.setItem('mvn_manager_storefront_v1:11:staff-7:main:lead-inbox', JSON.stringify({ search: 'Анна' }));
    const wrapper = mount(LeadInbox, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.get('input[type="search"]').element.value).toBe('Анна');
    const toggle = wrapper.get('button[aria-label="Поиск по входящим обращениям"]');
    expect(toggle.attributes('aria-expanded')).toBe('true');
    await wrapper.get('input[type="search"]').trigger('keydown', { key: 'Escape' });
    await new Promise(resolve => setTimeout(resolve, 320));
    await flushPromises();
    expect(wrapper.find('input[type="search"]').exists()).toBe(false);
    expect(toggle.attributes('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(toggle.element);
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
    await toggle.trigger('click');
    expect(document.activeElement).toBe(wrapper.get('input[type="search"]').element);
    wrapper.unmount();
  });

  it('refreshes unread source badges without closing the opened card', async () => {
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Непросмотренные')!.trigger('click');
    await flushPromises();
    const card = wrapper.findComponent({ name: 'LeadInboxCard' });
    card.vm.$emit('updated', { ...activeItem, is_read: true, is_new: false });
    await flushPromises();
    expect(wrapper.get('.channels .channel-count').text()).toBe('0');
    expect(wrapper.findComponent({ name: 'LeadInboxCard' }).vm).toBe(card.vm);
    card.vm.$emit('updated', { ...activeItem, is_read: false, is_new: true });
    await flushPromises();
    expect(wrapper.get('.channels .channel-count').text()).toBe('1');
    wrapper.unmount();
  });

  it('opens compact persistent incoming capture instead of creating an order', async () => {
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text().includes('Создать обращение'))!.trigger('click');
    expect(wrapper.get('[data-testid="quick-incoming"]').text()).toBe('new');
    expect(mocks.createManagerOrder).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('opens a quick incoming card for correction with its lead id', async () => {
    mocks.getLeadsInbox.mockResolvedValue(response([{ ...activeItem, id: 55, entity_kind: 'lead', intake_state: 'needs_contact' }]));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    await wrapper.get('[data-testid="edit-incoming"]').trigger('click');
    expect(wrapper.get('[data-testid="quick-incoming"]').text()).toBe('55');
    expect(window.location.search).toContain('incomingId=55');
    wrapper.unmount();
    window.history.replaceState({}, '', '/manager/leads');
  });

  it('opens a correction directly from an incomingId deep link', async () => {
    window.history.replaceState({}, '', '/manager/leads?incomingId=77');
    const wrapper = mount(LeadInbox);
    await flushPromises();
    expect(wrapper.get('[data-testid="quick-incoming"]').text()).toBe('77');
    wrapper.unmount();
    window.history.replaceState({}, '', '/manager/leads');
  });
  it('does not let an older personal counter overwrite the newest read decision', async () => {
    let resolveOld: ((value: { pending_count: number; unread_count: number; count: number }) => void) | undefined;
    mocks.getLeadsCounter.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    const wrapper = mount(LeadInbox);
    await flushPromises();
    const card = wrapper.findComponent({ name: 'LeadInboxCard' });
    card.vm.$emit('updated', { ...activeItem, is_read: true, is_new: false });
    card.vm.$emit('updated', { ...activeItem, is_read: false, is_new: true });
    await flushPromises();
    expect(wrapper.get('.inbox-header p').text()).toContain('Непросмотрено: 1');
    resolveOld?.({ pending_count: 1, unread_count: 0, count: 0 });
    await flushPromises();
    expect(wrapper.get('.inbox-header p').text()).toContain('Непросмотрено: 1');
    wrapper.unmount();
  });

  const inShell = async (showInbox = ref(true)) => {
    const theme = ref<'light' | 'dark'>('light');
    const Host = defineComponent({ setup: () => () => h(KitlaneShell, {
      name: 'Компания', contextKey: 'inbox-test', collapsed: false, mobileOpen: false,
      theme: theme.value, onToggleTheme: () => { theme.value = theme.value === 'light' ? 'dark' : 'light'; },
    }, {
      account: () => h(ManagerAccountMenu, { auth: { username: 'manager', display_name: 'Очень длинное имя ответственного менеджера', capabilities: [] } as never }),
      default: () => showInbox.value ? h(LeadInbox) : h('div', { 'data-testid': 'home' }, 'Главная'),
    }) });
    shellWrapper = mount(Host, { attachTo: document.body });
    await flushPromises();
    return shellWrapper;
  };

  it('teleports one inbox title and primary controls into the real shell and retains mail actions in content', async () => {
    const wrapper = await inShell();
    const header = wrapper.get('.kitlane-topbar');
    const content = wrapper.get('.inbox-workspace');
    expect(header.get('h1').text()).toBe('Входящие');
    expect(wrapper.findAll('h1')).toHaveLength(1);
    expect(content.find('h1').exists()).toBe(false);
    expect(header.get('button[aria-label="Активные"]').attributes('aria-pressed')).toBe('true');
    expect(header.get('button[aria-label="Архив"]').exists()).toBe(true);
    expect(header.get('button[aria-label="Поиск по входящим обращениям"]').exists()).toBe(true);
    expect(wrapper.findAll('button[aria-label="Создать обращение"]')).toHaveLength(1);
    expect(header.find('.channels').exists()).toBe(false);
    expect(header.find('button[aria-label="Проверить почту"]').exists()).toBe(false);
    expect(content.get('.channels').exists()).toBe(true);
    expect(content.get('select[aria-label="Сортировка входящих"]').exists()).toBe(true);
    await content.get('button[aria-label="Проверить почту"]').trigger('click');
    expect(content.get('[data-testid="email-import"]').text()).toBe('Импорт почты');
    await header.get('button[aria-label="Создать обращение"]').trigger('click');
    expect(content.get('[data-testid="quick-incoming"]').text()).toBe('new');
    expect(mocks.createManagerOrder).not.toHaveBeenCalled();
  });

  it('keeps teleported search focus, existing debounce, direct archive switch and Escape clearing', async () => {
    vi.useFakeTimers();
    const wrapper = await inShell();
    const header = wrapper.get('.kitlane-topbar');
    const toggle = header.get('button[aria-label="Поиск по входящим обращениям"]');
    await toggle.trigger('click');
    const input = header.get('input[type="search"]');
    expect(document.activeElement).toBe(input.element);
    await input.setValue('Анна');
    expect(mocks.getLeadsInbox).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(310); await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, 'Анна', undefined, false, 'deadline');
    await header.get('button[aria-label="Архив"]').trigger('click'); await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('archive', 1, 50, 'Анна', undefined, false, 'deadline');
    expect(header.get('button[aria-label="Архив"]').attributes('aria-pressed')).toBe('true');
    await input.trigger('keydown', { key: 'Escape' });
    await vi.advanceTimersByTimeAsync(310); await flushPromises();
    expect(header.find('input[type="search"]').exists()).toBe(false);
    expect(document.activeElement).toBe(toggle.element);
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('archive', 1, 50, undefined, undefined, false, 'deadline');
  });

  it('uses available header width for direct search and cleans up the observer and teleported nodes on navigation', async () => {
    let width = 270;
    let resizeControls = () => {};
    const disconnectControls = vi.fn();
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
      return { width: this.classList.contains('inbox-context') ? width : 0, height: 72 } as DOMRect;
    });
    vi.stubGlobal('ResizeObserver', class {
      isControls = false;
      constructor(private callback: () => void) {}
      observe(element: Element) { if (element.classList.contains('inbox-context')) { this.isControls = true; resizeControls = this.callback; } }
      disconnect() { if (this.isControls) disconnectControls(); }
    });
    const show = ref(true);
    const wrapper = await inShell(show);
    const header = wrapper.get('.kitlane-topbar');
    expect(header.find('input[type="search"]').exists()).toBe(false);
    width = 650; resizeControls(); await flushPromises();
    expect(header.get('.inbox-context-search').classes()).toContain('is-direct');
    expect(header.find('button[aria-label="Поиск по входящим обращениям"]').exists()).toBe(false);
    const input = header.get('input[type="search"]');
    await input.setValue('Анна'); await input.trigger('keydown', { key: 'Escape' });
    expect((input.element as HTMLInputElement).value).toBe('');
    expect(document.activeElement).toBe(input.element);
    width = 270; resizeControls(); await flushPromises();
    expect(header.get('.inbox-context-search').classes()).not.toContain('is-direct');
    expect(document.activeElement).toBe(input.element);
    expect(header.get('button[aria-label="Поиск по входящим обращениям"]').attributes('aria-expanded')).toBe('true');
    await header.get('button[aria-label="Тёмная тема"]').trigger('click');
    expect(header.get('button[aria-label="Светлая тема"]').exists()).toBe(true);
    expect(header.find('input[type="search"]').exists()).toBe(false);
    await header.get('button[aria-label^="Аккаунт:"]').trigger('click'); await flushPromises();
    expect(header.get('[role="menu"]').isVisible()).toBe(true);
    show.value = false; await flushPromises();
    expect(disconnectControls).toHaveBeenCalledOnce();
    expect(header.classes()).not.toContain('has-context-header');
    expect(header.find('.inbox-context').exists()).toBe(false);
    expect(wrapper.get('[data-testid="home"]').text()).toBe('Главная');
    show.value = true; await flushPromises();
    expect(header.findAll('h1')).toHaveLength(1);
    expect(header.findAll('button[aria-label="Создать обращение"]')).toHaveLength(1);
    expect(header.find('input[type="search"]').exists()).toBe(false);
    expect(header.get('button[aria-label="Поиск по входящим обращениям"]').attributes('aria-expanded')).toBe('false');
  });

  it('closes the compact search on account/outside clicks without clearing its query, and Escape returns focus once', async () => {
    vi.useFakeTimers();
    const wrapper = await inShell();
    const header = wrapper.get('.kitlane-topbar');
    const toggle = header.get('button[aria-label="Поиск по входящим обращениям"]');
    await toggle.trigger('click');
    await header.get('input[type="search"]').setValue('Анна');
    await vi.advanceTimersByTimeAsync(310); await flushPromises();
    const calls = mocks.getLeadsInbox.mock.calls.length;
    const account = header.get('button[aria-label^="Аккаунт:"]');
    (account.element as HTMLElement).focus();
    await account.trigger('click'); await flushPromises();
    expect(header.find('input[type="search"]').exists()).toBe(false);
    expect(header.get('[role="menu"]').isVisible()).toBe(true);
    expect(document.activeElement).toBe(account.element);
    expect(toggle.attributes('aria-pressed')).toBe('true');
    expect(mocks.getLeadsInbox.mock.calls).toHaveLength(calls);
    await account.trigger('click');
    await toggle.trigger('click');
    expect(header.get('input[type="search"]').element.value).toBe('Анна');
    (header.get('button[aria-label="Создать обращение"]').element as HTMLElement).focus();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    await flushPromises();
    expect(header.find('input[type="search"]').exists()).toBe(false);
    expect(document.activeElement).toBe(toggle.element);
    await vi.advanceTimersByTimeAsync(310); await flushPromises();
    expect(mocks.getLeadsInbox).toHaveBeenLastCalledWith('active', 1, 50, undefined, undefined, false, 'deadline');
  });

});
