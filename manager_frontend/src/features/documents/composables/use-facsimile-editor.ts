import { computed, onScopeDispose, ref } from 'vue';
import { facsimileApi } from '../integrations/facsimile-api';
import { constrainStamp, facsimileSavePayload, type FacsimileKind, type FacsimilePlacement, type FacsimilePreview, type StampPlacement } from '../model/facsimile-placement';

export const useFacsimileEditor = () => {
  const preview = ref<FacsimilePreview | null>(null);
  const placement = ref<FacsimilePlacement | null>(null);
  const currentPage = ref(1);
  const selected = ref<FacsimileKind>('signature');
  const pageUrl = ref('');
  const assetUrls = ref<Record<FacsimileKind, string>>({ signature: '', seal: '' });
  const loading = ref(false);
  const pageLoading = ref(false);
  const saving = ref(false);
  const error = ref('');
  let generation = 0;
  let pageGeneration = 0;
  let sessionController: AbortController | null = null;
  let pageController: AbortController | null = null;
  const page = computed(() => preview.value?.pages.find((item) => item.page_number === currentPage.value) || null);
  const clearPage = () => { if (pageUrl.value) URL.revokeObjectURL(pageUrl.value); pageUrl.value = ''; };
  const close = () => {
    generation++; pageGeneration++;
    sessionController?.abort(); pageController?.abort();
    clearPage();
    for (const url of Object.values(assetUrls.value)) if (url) URL.revokeObjectURL(url);
    assetUrls.value = { signature: '', seal: '' };
    preview.value = null; placement.value = null;
    loading.value = false; pageLoading.value = false; saving.value = false; error.value = '';
  };
  const setPage = async (number: number) => {
    if (!preview.value?.pages.some((item) => item.page_number === number)) return;
    currentPage.value = number;
    pageController?.abort();
    pageController = new AbortController();
    const controller = pageController;
    const requestId = ++pageGeneration;
    const sessionId = generation;
    const documentId = preview.value.document_id;
    clearPage(); pageLoading.value = true; error.value = '';
    try {
      const blob = await facsimileApi.page(documentId, number, controller.signal);
      if (requestId !== pageGeneration || sessionId !== generation) return;
      pageUrl.value = URL.createObjectURL(blob);
    } catch (cause) {
      if (requestId === pageGeneration && sessionId === generation && !controller.signal.aborted) error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить страницу';
    } finally { if (requestId === pageGeneration && sessionId === generation) pageLoading.value = false; }
  };
  const open = async (documentId: number) => {
    close();
    const requestId = generation;
    sessionController = new AbortController();
    const controller = sessionController;
    loading.value = true;
    try {
      const value = await facsimileApi.preview(documentId, controller.signal);
      if (requestId !== generation) return;
      if (!value.pages.length) throw new Error('В PDF нет страниц для размещения');
      const blobs = await Promise.all([
        facsimileApi.asset(documentId, value.signature.asset_id, controller.signal),
        facsimileApi.asset(documentId, value.seal.asset_id, controller.signal),
      ]);
      if (requestId !== generation) return;
      preview.value = value;
      placement.value = { signature: { ...value.placement.signature }, seal: { ...value.placement.seal } };
      for (const kind of ['signature', 'seal'] as const) {
        const targetPage = value.pages.find((item) => item.page_number === placement.value![kind].page_number) || value.pages[0]!;
        placement.value[kind] = constrainStamp(placement.value[kind], targetPage, value[kind]);
      }
      assetUrls.value = { signature: URL.createObjectURL(blobs[0]!), seal: URL.createObjectURL(blobs[1]!) };
      await setPage(placement.value.signature.page_number);
    } catch (cause) {
      if (requestId === generation && !controller.signal.aborted) error.value = cause instanceof Error ? cause.message : 'Не удалось открыть PDF';
    } finally { if (requestId === generation) loading.value = false; }
  };
  const updateStamp = (kind: FacsimileKind, value: StampPlacement) => {
    if (!preview.value || !placement.value || !page.value || saving.value || !preview.value.can_save) return;
    placement.value[kind] = constrainStamp(value, page.value, preview.value[kind]);
  };
  const save = async () => {
    if (!preview.value?.can_save || !placement.value || !pageUrl.value || loading.value || pageLoading.value || saving.value || error.value) return false;
    const requestId = generation;
    saving.value = true; error.value = '';
    try {
      await facsimileApi.save(preview.value.document_id, facsimileSavePayload(preview.value, placement.value), sessionController!.signal);
      return requestId === generation;
    } catch (cause) {
      if (requestId === generation && !sessionController?.signal.aborted) error.value = cause instanceof Error ? cause.message : 'Не удалось сохранить PDF';
      return false;
    } finally { if (requestId === generation) saving.value = false; }
  };
  onScopeDispose(close);
  return { preview, placement, page, currentPage, selected, pageUrl, assetUrls, loading, pageLoading, saving, error, open, close, setPage, updateStamp, save };
};
