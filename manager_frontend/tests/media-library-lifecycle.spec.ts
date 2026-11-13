import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerMediaAssetListResponse, ManagerMediaAssetResponse, ManagerMediaProcessingJobResponse } from '../src/api';

const mocks = vi.hoisted(() => ({ assets: vi.fn(), config: vi.fn(), jobs: vi.fn() }));
vi.mock('../src/api', () => ({ api: {
  listMediaAssets: mocks.assets,
  getMediaBackgroundRemovalConfig: mocks.config,
  listMediaProcessingJobs: mocks.jobs,
} }));
import MediaLibraryView from '../src/views/MediaLibraryView.vue';

enableAutoUnmount(afterEach);
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
};
const asset = (id: number, title: string): ManagerMediaAssetResponse => ({
  id, title, kind: 'product', tags: ['монтаж'], variant_type: 'original', url: `/media/${id}.jpg`,
  mime_type: 'image/jpeg', storage_provider: 'local', processing_status: 'ready',
  created_at: '2026-11-13T10:00:00Z', updated_at: '2026-11-13T10:00:00Z',
});
const result = (title: string, total = 81, pages = 3, id = 1): ManagerMediaAssetListResponse => ({
  items: [asset(id, title)], meta: { page: 1, limit: 40, total, pages },
});
const job = (status: string): ManagerMediaProcessingJobResponse => ({
  job_id: 'job-1', source_asset_id: 1, operation: 'background_removal', status, stage: status,
  priority: 100, attempts: 1, created_at: '2026-11-13T10:00:00Z', updated_at: '2026-11-13T10:00:00Z',
});
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find(item => item.text() === text)!;
const submit = (wrapper: VueWrapper) => wrapper.get('input[type="search"]').trigger('keydown.enter');
const filter = (wrapper: VueWrapper, label: string) => wrapper.findAll('select').find(item => item.text().includes(label))!;

beforeEach(() => {
  vi.resetAllMocks();
  vi.useFakeTimers();
  mocks.assets.mockResolvedValue(result('Сохранённые файлы'));
  mocks.config.mockResolvedValue({});
  mocks.jobs.mockResolvedValue({ items: [] });
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('media library request lifecycle', () => {
  it('keeps the latest page assets and pagination when the previous page resolves last', async () => {
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    const old = deferred<ManagerMediaAssetListResponse>();
    const current = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await button(wrapper, 'Вперед').trigger('click');
    await button(wrapper, 'Вперед').trigger('click');
    expect(mocks.assets).toHaveBeenNthCalledWith(2, expect.objectContaining({ page: 2 }));
    expect(mocks.assets).toHaveBeenNthCalledWith(3, expect.objectContaining({ page: 3 }));

    current.resolve(result('Последняя страница', 394, 10));
    await flushPromises();
    old.resolve(result('Устаревшая страница', 42, 2));
    await flushPromises();
    expect(wrapper.get('article').text()).toContain('Последняя страница');
    expect(wrapper.text()).toContain('394 файлов');
    expect(wrapper.text()).toContain('Страница 3 из 10');
  });

  it('keeps the latest submitted filter results and refreshes a selected asset only from that response', async () => {
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    await wrapper.get('article').trigger('click');
    const old = deferred<ManagerMediaAssetListResponse>();
    const current = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    await wrapper.get('input[type="search"]').setValue('старый');
    await submit(wrapper);
    await wrapper.get('input[type="search"]').setValue('  новый  ');
    await filter(wrapper, 'Все типы').setValue('article');
    await filter(wrapper, 'Все теги').setValue('монтаж');
    await filter(wrapper, 'Все статусы').setValue('ready');
    await submit(wrapper);
    expect(mocks.assets).toHaveBeenLastCalledWith({ page: 1, limit: 40, q: 'новый', kind: 'article', tag: 'монтаж', status: 'ready' });
    current.resolve(result('Свежие метаданные', 1, 1));
    await flushPromises();
    old.resolve(result('Устаревшие метаданные', 99, 3));
    await flushPromises();
    expect(wrapper.get('article').text()).toContain('Свежие метаданные');
    expect(wrapper.get('aside').text()).toContain('Свежие метаданные');
    expect(wrapper.text()).not.toContain('Устаревшие метаданные');
    expect(wrapper.text()).toContain('1 файлов');
    expect(wrapper.text()).toContain('Страница 1 из 1');
  });

  it.each(['success', 'failure'] as const)('does not let stale %s clear a current loading state or show an obsolete error', async outcome => {
    const old = deferred<ManagerMediaAssetListResponse>();
    const current = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const wrapper = mount(MediaLibraryView);
    await submit(wrapper);
    if (outcome === 'success') old.resolve(result('Устаревшие файлы'));
    else old.reject(new Error('Устаревшая ошибка'));
    await flushPromises();
    expect(button(wrapper, 'Ищу...').attributes('disabled')).toBeDefined();
    expect(wrapper.find('article').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Устаревшая ошибка');
    expect(wrapper.text()).toContain('0 файлов');
    current.resolve(result('Актуальные файлы'));
    await flushPromises();
    expect(wrapper.get('article').text()).toContain('Актуальные файлы');
    expect(button(wrapper, 'Найти').attributes('disabled')).toBeUndefined();
  });

  it('keeps the current error when an obsolete request fails afterward', async () => {
    const old = deferred<ManagerMediaAssetListResponse>();
    const current = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const wrapper = mount(MediaLibraryView);
    await submit(wrapper);
    current.reject(new Error('Ошибка текущего поиска'));
    await flushPromises();
    old.reject(new Error('Устаревшая ошибка'));
    await flushPromises();
    expect(wrapper.text()).toContain('Ошибка текущего поиска');
    expect(wrapper.text()).not.toContain('Устаревшая ошибка');
    expect(button(wrapper, 'Найти').attributes('disabled')).toBeUndefined();
  });

  it.each(['query', 'kind', 'tag', 'status'])('invalidates a pending read when %s changes before another search starts', async field => {
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    const old = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise);
    await submit(wrapper);
    if (field === 'query') await wrapper.get('input[type="search"]').setValue('новый запрос');
    if (field === 'kind') await filter(wrapper, 'Все типы').setValue('article');
    if (field === 'tag') await filter(wrapper, 'Все теги').setValue('монтаж');
    if (field === 'status') await filter(wrapper, 'Все статусы').setValue('failed');
    expect(mocks.assets).toHaveBeenCalledTimes(2);
    old.resolve(result('Устаревшие файлы', 99, 4));
    await flushPromises();
    expect(wrapper.get('article').text()).toContain('Сохранённые файлы');
    expect(wrapper.text()).toContain('81 файлов');
    expect(wrapper.text()).toContain('Страница 1 из 3');
    expect(button(wrapper, 'Найти').attributes('disabled')).toBeUndefined();
  });

  it('discards a queued old rejection immediately on input and enables the next explicit search', async () => {
    const old = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise);
    const wrapper = mount(MediaLibraryView);
    old.reject(new Error('Ошибка прежнего запроса'));
    const input = wrapper.get('input[type="search"]');
    (input.element as HTMLInputElement).value = 'новый';
    await input.trigger('input');
    await flushPromises();
    expect(wrapper.text()).not.toContain('Ошибка прежнего запроса');
    await button(wrapper, 'Найти').trigger('click');
    await flushPromises();
    expect(mocks.assets).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'новый' }));
  });

  it('keeps a pending response invalid after input changes away and back within the same tick', async () => {
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    const old = deferred<ManagerMediaAssetListResponse>();
    mocks.assets.mockReturnValueOnce(old.promise);
    await submit(wrapper);
    old.resolve(result('Устаревший снимок'));
    const input = wrapper.get('input[type="search"]').element as HTMLInputElement;
    input.value = 'временный запрос';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flushPromises();
    expect(mocks.assets).toHaveBeenCalledTimes(2);
    expect(wrapper.get('article').text()).toContain('Сохранённые файлы');
    expect(button(wrapper, 'Найти').attributes('disabled')).toBeUndefined();
  });

  it('preserves a selected asset absent from the next result and returns searches to page one', async () => {
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    await wrapper.get('article').trigger('click');
    await button(wrapper, 'Вперед').trigger('click');
    await flushPromises();
    mocks.assets.mockResolvedValueOnce(result('Другой файл', 1, 1, 2));
    await wrapper.get('input[type="search"]').setValue('другой');
    await submit(wrapper);
    await flushPromises();
    expect(mocks.assets).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, q: 'другой' }));
    expect(wrapper.get('article').text()).toContain('Другой файл');
    expect(wrapper.get('aside').text()).toContain('Сохранённые файлы');
    expect(wrapper.text()).toContain('Страница 1 из 1');
  });

  it('refreshes assets after an active processing job finishes and stops polling inactive jobs', async () => {
    mocks.jobs.mockResolvedValueOnce({ items: [job('running')] }).mockResolvedValue({ items: [job('success')] });
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    await wrapper.get('article').trigger('click');
    expect(wrapper.get('aside').text()).toContain('Текущий файл: в работе');
    await vi.advanceTimersByTimeAsync(8000);
    await flushPromises();
    expect(mocks.assets).toHaveBeenCalledTimes(2);
    expect(wrapper.get('aside').text()).not.toContain('Текущий файл: в работе');
    await vi.advanceTimersByTimeAsync(8000);
    expect(mocks.jobs).toHaveBeenCalledTimes(2);
  });

  it('does not refresh assets when a pending job poll finishes after unmount', async () => {
    const pending = deferred<{ items: ManagerMediaProcessingJobResponse[] }>();
    mocks.jobs.mockResolvedValueOnce({ items: [job('running')] }).mockReturnValueOnce(pending.promise);
    const wrapper = mount(MediaLibraryView);
    await flushPromises();
    await vi.advanceTimersByTimeAsync(8000);
    wrapper.unmount();
    pending.resolve({ items: [job('success')] });
    await flushPromises();
    await vi.advanceTimersByTimeAsync(16000);
    expect(mocks.assets).toHaveBeenCalledOnce();
    expect(mocks.jobs).toHaveBeenCalledTimes(2);
  });

  it('does not report late read failures or schedule a toast after unmount', async () => {
    const assets = deferred<ManagerMediaAssetListResponse>();
    const jobs = deferred<{ items: ManagerMediaProcessingJobResponse[] }>();
    const config = deferred<{}>();
    mocks.assets.mockReturnValueOnce(assets.promise);
    mocks.jobs.mockReturnValueOnce(jobs.promise);
    mocks.config.mockReturnValueOnce(config.promise);
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const wrapper = mount(MediaLibraryView);
    wrapper.unmount();
    const timeout = vi.spyOn(window, 'setTimeout');
    assets.reject(new Error('Поздняя ошибка файлов'));
    jobs.reject(new Error('Поздняя ошибка очереди'));
    config.reject(new Error('Поздняя ошибка настроек'));
    await flushPromises();
    expect(timeout).not.toHaveBeenCalled();
    expect(warning).not.toHaveBeenCalled();
  });
});
