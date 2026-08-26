import type { Ref } from 'vue';
import { ManagerDocsService } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';

export const useExternalContractRegistration = (options: {
  orderId: () => number;
  canCreate: () => boolean;
  accessSummary: () => string;
  number: Ref<string>;
  date: Ref<string>;
  url: Ref<string>;
  file: Ref<File | null>;
  isOpen: Ref<boolean>;
  isSaving: Ref<boolean>;
  loadDocuments: () => Promise<void>;
  clearSelectedCustomerContract: () => void;
  refresh: () => void;
  notify: (message: string, type?: 'success' | 'error') => void;
}) => {
  const handleExternalContractFile = (event: Event) => {
    options.file.value = (event.target as HTMLInputElement).files?.[0] || null;
  };

  const reset = () => {
    options.number.value = '';
    options.date.value = new Date().toISOString().slice(0, 10);
    options.url.value = '';
    options.file.value = null;
  };

  const registerExternalContract = async () => {
    if (!options.canCreate()) return options.notify(options.accessSummary(), 'error');
    const number = options.number.value.trim();
    if (!number) return options.notify('Укажите номер договора', 'error');
    if (!options.date.value) return options.notify('Укажите дату договора', 'error');
    options.isSaving.value = true;
    try {
      await ManagerDocsService.registerManagerExternalContract(options.orderId(), {
        number,
        contract_date: `${options.date.value}T00:00:00`,
        external_url: options.url.value.trim() || undefined,
        file: options.file.value || undefined,
      });
      await options.loadDocuments();
      options.clearSelectedCustomerContract();
      options.isOpen.value = false;
      reset();
      options.refresh();
      options.notify('Внешний договор добавлен');
    } catch (error) {
      options.notify(`Ошибка добавления договора: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      options.isSaving.value = false;
    }
  };

  return { handleExternalContractFile, registerExternalContract };
};
