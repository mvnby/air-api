import type {
  LeadCreatePayload,
  LeadQualifyPayload,
  ManagerCatalogCustomerItemResponse,
} from '../client';
import { normalizePhoneForApi } from './phone';

export function mapCustomerToLeadCreatePrefill(
  customer: ManagerCatalogCustomerItemResponse,
): Partial<LeadCreatePayload> {
  return {
    name: customer.name || undefined,
    phone: customer.phone ? normalizePhoneForApi(customer.phone) : undefined,
    email: customer.email || undefined,
    inn: customer.inn || undefined,
    company_name: customer.full_legal_name || customer.name || undefined,
  };
}

export function mapCustomerToLeadQualifyPrefill(
  customer: ManagerCatalogCustomerItemResponse,
): Partial<LeadQualifyPayload> {
  return {
    name: customer.name || undefined,
    phone: customer.phone ? normalizePhoneForApi(customer.phone) : undefined,
    email: customer.email || undefined,
    inn: customer.inn || undefined,
    full_legal_name: customer.full_legal_name || undefined,
    legal_address: customer.legal_address || undefined,
    iban: customer.iban || undefined,
    bic: customer.bic || undefined,
    bank_name: customer.bank_name || undefined,
    delivery_address: customer.last_delivery_address || customer.actual_address || undefined,
  };
}
