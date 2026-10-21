import { onScopeDispose, watch, type Ref } from 'vue';

type TitleRole = 'identity' | 'page';
const titles = new Map<symbol, { role: TitleRole; value: string | null }>();

// Identity and the active page share one writer so a late brand response cannot replace the order title.
const renderTitle = () => {
  const entries = [...titles.values()].reverse();
  const page = entries.find(entry => entry.role === 'page' && entry.value);
  const identity = entries.find(entry => entry.role === 'identity' && entry.value);
  const title = page?.value || identity?.value;
  document.title = title ? `${title} · KitLane` : 'KitLane';
};

export const useManagerDocumentTitle = (title: Readonly<Ref<string | null | undefined>>, role: TitleRole = 'page') => {
  const owner = Symbol('manager-document-title');
  const stop = watch(title, value => {
    titles.set(owner, { role, value: value?.trim() || null });
    renderTitle();
  }, { immediate: true, flush: 'sync' });
  onScopeDispose(() => {
    stop();
    titles.delete(owner);
    renderTitle();
  });
};
