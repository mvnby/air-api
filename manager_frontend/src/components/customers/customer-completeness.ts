import type { ManagerCatalogCustomerItemResponse, ManagerCustomerContactItemResponse } from '../../client';

export type SavedContacts = { customerId: number; items: ManagerCustomerContactItemResponse[] | null };
export type CompletenessGroup = { id: string; label: string; missing: string[]; note?: string; applicable: boolean };
const present = (value: unknown) => typeof value === 'string' && value.trim().length > 0;

// This is a projection of saved fields, never document validation or proof of authority.
export function customerCompleteness(customer: ManagerCatalogCustomerItemResponse, contacts?: SavedContacts | null): CompletenessGroup[] {
  const business = customer.type === 'company' || customer.type === 'individual_entrepreneur';
  const representative = customer.signing_mode === 'power_of_attorney';
  const company = customer.type === 'company';
  const knownContacts = contacts?.customerId === customer.id ? contacts.items : null;
  const active = (knownContacts ?? [customer.primary_contact]).filter((c): c is ManagerCustomerContactItemResponse => !!c && c.is_active !== false);
  const phone = present(customer.phone) || active.some(c => present(c.phone));
  const email = present(customer.email) || active.some(c => present(c.email));
  const additionalUnknown = knownContacts === null && (customer.contact_count ?? 0) > active.length;
  const fields = (entries: Array<[unknown, string]>) => entries.filter(([value]) => !present(value)).map(([, label]) => label);
  const validMode = representative || (company ? customer.signing_mode === 'statutory_body' : customer.signing_mode === 'self');
  return [
    { id: 'contacts', label: 'Контакты', applicable: true,
      missing: additionalUnknown ? [] : fields([[phone ? 'yes' : null, 'телефон'], [email ? 'yes' : null, 'email']]),
      note: additionalUnknown ? 'Дополнительные контакты ещё не загружены; откройте «Контакты и реквизиты».' : undefined },
    { id: 'identity', label: company ? 'Данные организации' : business ? 'Данные ИП' : 'Данные организации / ИП', applicable: business,
      missing: business ? fields([[customer.full_legal_name, 'полное наименование'], [customer.inn, 'УНП']]) : [] },
    { id: 'bank', label: 'Банковские сведения', applicable: business,
      missing: business ? fields([[customer.bank_name, 'название банка'], [customer.bic, 'BIC'], [customer.iban, 'IBAN']]) : [] },
    { id: 'signer', label: 'Подписант', applicable: true,
      missing: [
        ...(!validMode ? ['допустимый режим подписания'] : []),
        ...fields([[business || representative ? customer.signer_name : customer.name, representative ? 'ФИО представителя' : business ? 'ФИО подписанта' : 'ФИО клиента']]),
        ...(representative ? fields([[customer.acting_basis, 'основание полномочий представителя']]) : company ? fields([[customer.signer_position, 'должность подписанта'], [customer.acting_basis, 'основание полномочий']]) : []),
      ],
      note: 'Сохранённые поля и режим подписания не подтверждают полномочия.' },
    { id: 'addresses', label: 'Адреса', applicable: true,
      missing: business ? fields([[customer.legal_address, 'юридический адрес'], [customer.actual_address, 'фактический / почтовый адрес']])
        : fields([[present(customer.actual_address) ? customer.actual_address : customer.last_delivery_address, 'адрес объекта / доставки']]) },
  ];
}
