import { computed, useTemplateRef } from 'vue';
import { confirmDialog } from '../services/ui-feedback';

type CatalogDocumentsEditor = {
  isDirty: boolean;
  isBusy: boolean;
  save: () => Promise<boolean>;
};

export const useCatalogDocumentsEditor = () => {
  const documentsPanel = useTemplateRef<CatalogDocumentsEditor>('documentsPanel');
  const documentsDirty = computed(() => Boolean(documentsPanel.value?.isDirty));
  const documentsBusy = computed(() => Boolean(documentsPanel.value?.isBusy));
  const saveDocuments = async (): Promise<boolean> => documentsPanel.value ? documentsPanel.value.save() : true;
  const confirmDiscardDocuments = async (): Promise<boolean> => {
    if (documentsBusy.value) return false;
    if (!documentsDirty.value) return true;
    return confirmDialog({
      title: 'Закрыть без сохранения документов?',
      description: 'Изменения списка документов будут потеряны.',
      confirmText: 'Закрыть без сохранения',
      variant: 'warning',
    });
  };
  return { documentsDirty, documentsBusy, saveDocuments, confirmDiscardDocuments };
};
