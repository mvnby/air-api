import type { Ref } from 'vue';
import { ManagerDocsService } from '../../../client';
import type { ManagerOrderDocumentItem } from '../../../client';
import { downloadManagerDocBlob } from '../../../api';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { confirmDialog } from '../../../services/ui-feedback';

type DocumentAccess = { canUpload: boolean; canReplace: boolean; canDelete: boolean; summary: string };

export const useDocumentFileActions = (options: {
  orderId: () => number;
  access: Ref<DocumentAccess>;
  fileInput: Ref<HTMLInputElement | null>;
  isUploading: Ref<boolean>;
  processingDocumentId: Ref<number | null>;
  loadDocuments: () => Promise<void>;
  refresh: () => void;
  notify: (message: string, type?: 'success' | 'error') => void;
}) => {
  const triggerFileUpload = () => {
    if (!options.access.value.canUpload) {
      options.notify(options.access.value.summary, 'error');
      return;
    }
    options.fileInput.value?.click();
  };

  const handleFileUpload = async (event: Event) => {
    if (!options.access.value.canUpload) return;
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    options.isUploading.value = true;
    try {
      await ManagerDocsService.uploadManagerOrderDocument(options.orderId(), { file });
      await options.loadDocuments();
      options.refresh();
      options.notify('Документ загружен');
    } catch (error) {
      options.notify(`Ошибка загрузки: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      options.isUploading.value = false;
      if (options.fileInput.value) options.fileInput.value.value = '';
    }
  };

  const handleAttachDocumentFile = async (doc: ManagerOrderDocumentItem, event: Event) => {
    if (!options.access.value.canReplace) return;
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    options.processingDocumentId.value = doc.id;
    try {
      await ManagerDocsService.attachManagerDocFile(doc.id, { file });
      await options.loadDocuments();
      options.refresh();
      options.notify('Файл прикреплен');
    } catch (error) {
      options.notify(`Ошибка прикрепления: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      options.processingDocumentId.value = null;
      target.value = '';
    }
  };

  const downloadDocument = async (doc: ManagerOrderDocumentItem) => {
    options.processingDocumentId.value = doc.id;
    try {
      const { blob, filename } = await downloadManagerDocBlob(doc.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename || `${doc.number || doc.doc_type}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      options.notify(`Ошибка скачивания: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      options.processingDocumentId.value = null;
    }
  };

  const deleteDocument = async (docId: number) => {
    if (!options.access.value.canDelete) {
      options.notify(options.access.value.summary, 'error');
      return;
    }
    if (!await confirmDialog({ title: 'Удалить документ?', confirmText: 'Удалить', variant: 'danger' })) return;
    options.processingDocumentId.value = docId;
    try {
      await ManagerDocsService.deleteManagerDoc(docId);
      await options.loadDocuments();
      options.refresh();
      options.notify('Документ удален');
    } catch {
      options.notify('Ошибка удаления', 'error');
    } finally {
      options.processingDocumentId.value = null;
    }
  };

  return { triggerFileUpload, handleFileUpload, handleAttachDocumentFile, downloadDocument, deleteDocument };
};
