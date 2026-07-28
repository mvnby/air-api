import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeadsInboxItemResponse } from '../src/api';
import LeadInboxCard from '../src/components/leads/LeadInboxCard.vue';
import { serviceAttachmentsApi } from '../src/components/service-attachments/api';
import type { ServiceAttachmentItem } from '../src/components/service-attachments/types';

vi.mock('../src/components/service-attachments/api', () => ({
  serviceAttachmentsApi: {
    list: vi.fn(),
    listEquipment: vi.fn(),
    upload: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    getAccess: vi.fn(),
  },
}));

const lead: LeadsInboxItemResponse = {
  id: 42,
  status: 'new_lead',
  is_new: true,
  customer_name: 'Анна',
  phone: '+375291112233',
  source: 'site',
  comment: 'Нужно оценить место монтажа',
  created_at: '2026-07-28T09:00:00Z',
  attachment_count: 1,
};

const attachment: ServiceAttachmentItem = {
  id: 701,
  file_kind: 'image',
  category: 'installation_indoor',
  filename: 'indoor-unit.webp',
  mime_type: 'image/webp',
  size_bytes: 128_000,
  caption: 'Место внутреннего блока',
  transcript: null,
  source: 'website_installation_estimate',
  processing_status: 'ready',
  processing_error: null,
  captured_at: null,
  created_at: '2026-07-28T09:00:00Z',
  preview_available: true,
};

const secondAttachment: ServiceAttachmentItem = {
  ...attachment,
  id: 702,
  filename: 'facade.webp',
  caption: 'Фасад здания',
  category: 'installation_facade',
};

const listMock = vi.mocked(serviceAttachmentsApi.list);
const getAccessMock = vi.mocked(serviceAttachmentsApi.getAccess);
const uploadMock = vi.mocked(serviceAttachmentsApi.upload);
const updateMock = vi.mocked(serviceAttachmentsApi.update);
const removeMock = vi.mocked(serviceAttachmentsApi.remove);
const mountedWrappers: VueWrapper[] = [];

const mountCard = () => {
  const wrapper = mount(LeadInboxCard, {
    attachTo: document.body,
    props: { item: lead },
  });
  mountedWrappers.push(wrapper);
  return wrapper;
};

const openAttachments = async (wrapper: VueWrapper) => {
  const trigger = wrapper.get(`button[aria-controls="lead-attachments-${lead.id}"]`);
  await trigger.trigger('click');
  await flushPromises();
  return trigger;
};

const expectNoWrites = () => {
  expect(uploadMock).not.toHaveBeenCalled();
  expect(updateMock).not.toHaveBeenCalled();
  expect(removeMock).not.toHaveBeenCalled();
};

beforeEach(() => {
  vi.clearAllMocks();
  listMock.mockResolvedValue({ items: [attachment], total: 1 });
  getAccessMock.mockImplementation(async (_attachmentId, variant) => ({
    url: `https://private.example/${variant}.webp`,
    expires_at: '2026-07-28T09:05:00Z',
    variant,
  }));
});

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  document.body.innerHTML = '';
});

describe('LeadInboxCard read-only attachments', () => {
  it('opens photos before qualification and restores focus after the viewer closes', async () => {
    const wrapper = mountCard();
    expect(wrapper.find('[data-testid="lead-readonly-attachments"]').exists()).toBe(false);

    const disclosure = await openAttachments(wrapper);

    expect(disclosure.attributes('aria-expanded')).toBe('true');
    expect(listMock).toHaveBeenCalledWith(lead.id);
    expect(wrapper.get('[data-testid="lead-readonly-attachments"]').text()).toContain(attachment.caption);
    expect(wrapper.find('input[type="file"]').exists()).toBe(false);

    const panel = wrapper.get('[data-testid="lead-readonly-attachments"] section');
    const droppedFile = new File(['image'], 'dropped.png', { type: 'image/png' });
    await panel.trigger('drop', { dataTransfer: { files: [droppedFile] } });
    await panel.trigger('paste', {
      clipboardData: {
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => droppedFile }],
      },
    });

    const photoButton = wrapper.get(`button[aria-label="Открыть ${attachment.caption}"]`);
    (photoButton.element as HTMLButtonElement).focus();
    await photoButton.trigger('click');
    await flushPromises();

    const viewer = document.body.querySelector<HTMLElement>('[role="dialog"]');
    expect(viewer).not.toBeNull();
    expect(viewer?.querySelector('img')?.getAttribute('src')).toBe('https://private.example/original.webp');
    expect(viewer?.querySelector('img')?.getAttribute('referrerpolicy')).toBe('no-referrer');

    viewer?.querySelector<HTMLButtonElement>('button[aria-label="Закрыть"]')?.click();
    await flushPromises();

    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(photoButton.element);
    expect(wrapper.emitted('qualify')).toBeUndefined();
    expect(wrapper.emitted('reject')).toBeUndefined();
    expect(wrapper.emitted('no-answer')).toBeUndefined();
    expectNoWrites();

    listMock.mockRejectedValueOnce(new Error('Обновление временно недоступно'));
    await wrapper.get('button[aria-label="Обновить фото и файлы"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('img[referrerpolicy="no-referrer"]').attributes('src'))
      .toBe('https://private.example/preview.webp');

    await disclosure.trigger('click');
    expect(wrapper.find('[data-testid="lead-readonly-attachments"]').exists()).toBe(false);
    await wrapper.get('button[title="Квалифицировать (в сделку)"]').trigger('click');
    await wrapper.get('button[title="Отмена / В архив"]').trigger('click');
    expect(wrapper.emitted('qualify')).toEqual([[lead]]);
    expect(wrapper.emitted('reject')).toEqual([[lead]]);
    expectNoWrites();
  });

  it('shows a retryable list error without changing CRM state', async () => {
    listMock
      .mockRejectedValueOnce(new Error('Список временно недоступен'))
      .mockResolvedValueOnce({ items: [], total: 0 });
    const wrapper = mountCard();

    await openAttachments(wrapper);

    expect(wrapper.get('[role="alert"]').text()).toContain('Список временно недоступен');
    const retry = wrapper.findAll('button').find((button) => button.text().includes('Повторить'));
    expect(retry).toBeDefined();
    await retry?.trigger('click');
    await flushPromises();

    expect(listMock).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('В этой заявке нет доступных вложений');
    expectNoWrites();
  });

  it('keeps access failures inside the viewer and retries with GET only', async () => {
    getAccessMock.mockImplementation(async (_attachmentId, variant) => {
      if (variant === 'preview') {
        return {
          url: 'https://private.example/preview.webp',
          expires_at: '2026-07-28T09:05:00Z',
          variant,
        };
      }
      throw new Error('Приватный файл временно недоступен');
    });
    const wrapper = mountCard();

    await openAttachments(wrapper);
    await wrapper.get(`button[aria-label="Открыть ${attachment.caption}"]`).trigger('click');
    await flushPromises();

    const viewer = document.body.querySelector<HTMLElement>('[role="dialog"]');
    expect(viewer?.textContent).toContain('Файл не открылся');
    expect(viewer?.textContent).toContain('Приватный файл временно недоступен');

    viewer?.querySelector<HTMLButtonElement>('button')?.focus();
    const retry = [...(viewer?.querySelectorAll<HTMLButtonElement>('button') || [])]
      .find((button) => button.textContent?.includes('Повторить'));
    retry?.click();
    await flushPromises();

    const originalAccessCalls = getAccessMock.mock.calls
      .filter(([, variant]) => variant === 'original');
    expect(originalAccessCalls).toHaveLength(2);
    expectNoWrites();
  });

  it('leaves browser shortcuts untouched while the viewer is open', async () => {
    listMock.mockResolvedValue({ items: [attachment, secondAttachment], total: 2 });
    const wrapper = mountCard();

    await openAttachments(wrapper);
    await wrapper.get(`button[aria-label="Открыть ${attachment.caption}"]`).trigger('click');
    await flushPromises();

    const ctrlZoom = new KeyboardEvent('keydown', {
      key: '+',
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(ctrlZoom);
    const altNext = new KeyboardEvent('keydown', {
      key: 'ArrowRight',
      altKey: true,
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(altNext);
    await flushPromises();

    const viewer = document.body.querySelector<HTMLElement>('[role="dialog"]');
    expect(ctrlZoom.defaultPrevented).toBe(false);
    expect(altNext.defaultPrevented).toBe(false);
    expect(viewer?.textContent).toContain(attachment.filename);
    expect(viewer?.textContent).toContain('100%');
    expectNoWrites();
  });
});
