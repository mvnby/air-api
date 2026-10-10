import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DraftParametersEditor from '../src/features/documents/components/DraftParametersEditor.vue';
import { ManagerDocumentSystemService, type ManagedDocumentItem } from '../src/client';

const { confirmDialog } = vi.hoisted(() => ({ confirmDialog: vi.fn() }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog }));
const wrappers: VueWrapper[] = [];
const document = { id: 77, order_id: 42, doc_type: 'contract', status: 'draft', date: '2026-10-09T00:00:00' } as ManagedDocumentItem;
beforeEach(() => {
  confirmDialog.mockReset().mockResolvedValue(true);
  vi.spyOn(ManagerDocumentSystemService, 'getManagerManagedDocumentDraftParameters').mockResolvedValue({
    issue_date: '2026-10-09', issue_city: 'Витебск', revision: 'a'.repeat(64), has_editable_copy: true, total_amount: '1000.00',
  });
  vi.spyOn(ManagerDocumentSystemService, 'updateManagerManagedDocumentDraftParameters').mockResolvedValue(document);
});
afterEach(() => { wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); vi.restoreAllMocks(); });
const mountEditor = async () => {
  const wrapper = mount(DraftParametersEditor, { props: { document } });
  wrappers.push(wrapper); await flushPromises(); return wrapper;
};

describe('saved draft parameters', () => {
  it('saves a changed date on the existing draft without resetting manual edits', async () => {
    const wrapper = await mountEditor();
    await wrapper.get('[data-testid="draft-issue-date"]').setValue('2026-10-01');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(confirmDialog).not.toHaveBeenCalled();
    expect(ManagerDocumentSystemService.updateManagerManagedDocumentDraftParameters).toHaveBeenCalledWith(77, {
      issue_date: '2026-10-01', expected_revision: 'a'.repeat(64), reset_editable_copy: false,
    });
    expect(wrapper.emitted('saved')).toEqual([[false]]);
  });

  it('requires explicit confirmation before rebuilding an edited working copy', async () => {
    const wrapper = await mountEditor();
    await wrapper.get('[data-testid="draft-issue-city"]').setValue('Минск');
    confirmDialog.mockResolvedValueOnce(false);
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(ManagerDocumentSystemService.updateManagerManagedDocumentDraftParameters).not.toHaveBeenCalled();
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ title: 'Пересобрать рабочую копию?' }));
    expect(ManagerDocumentSystemService.updateManagerManagedDocumentDraftParameters).toHaveBeenCalledWith(77, {
      issue_city: 'Минск', expected_revision: 'a'.repeat(64), reset_editable_copy: true,
    });
  });

  it('keeps entered data when another tab already changed the draft', async () => {
    vi.mocked(ManagerDocumentSystemService.updateManagerManagedDocumentDraftParameters).mockRejectedValue(new Error('Параметры уже изменены в другой вкладке'));
    const wrapper = await mountEditor();
    await wrapper.get('[data-testid="draft-issue-date"]').setValue('2026-10-01');
    await wrapper.get('form').trigger('submit'); await flushPromises();
    expect(wrapper.get<HTMLInputElement>('[data-testid="draft-issue-date"]').element.value).toBe('2026-10-01');
    expect(wrapper.get('[role="alert"]').text()).toContain('другой вкладке');
    expect(wrapper.emitted('saved')).toBeUndefined();
  });
});
