import { describe, expect, it } from 'vitest';
import {
  businessTermsValidationError,
  createDefaultBusinessDocumentTerms,
  serializeBusinessTerms,
} from '../src/features/documents/model/business-document-terms';

describe('business document terms', () => {
  it('keeps the contract scenario on a contract snapshot', () => {
    const terms = {
      ...createDefaultBusinessDocumentTerms(),
      contract_scenario: 'supply_installation' as const,
      goods_warranty_months: 36,
      work_warranty_months: 12,
    };

    expect(serializeBusinessTerms('contract', terms)).toEqual(expect.objectContaining({
      contract_scenario: 'supply_installation',
      goods_warranty_months: 36,
      work_warranty_months: 12,
    }));
  });

  it('does not put incompatible clauses into an offer, invoice, or act', () => {
    const terms = {
      ...createDefaultBusinessDocumentTerms(),
      contract_scenario: 'repair' as const,
      payment_schedule: [{
        share_percent: 100,
        due_event: 'after_work' as const,
        due_days: null,
        due_day_kind: 'banking' as const,
        note: 'Оплата после диагностики.',
      }],
      goods_warranty_months: 24,
      work_warranty_months: 6,
    };

    const offer = serializeBusinessTerms('offer', terms);
    const act = serializeBusinessTerms('act', terms);

    expect(offer).toEqual(expect.objectContaining({
      payment_schedule: expect.arrayContaining([
        expect.objectContaining({ note: 'Оплата после диагностики.' }),
      ]),
    }));
    expect(offer).not.toHaveProperty('contract_scenario');
    expect(offer).not.toHaveProperty('goods_warranty_months');
    expect(act).toEqual(expect.objectContaining({
      goods_warranty_months: 24,
      work_warranty_months: 6,
    }));
    expect(act).not.toHaveProperty('payment_schedule');
    expect(act).not.toHaveProperty('contract_scenario');
  });

  it('blocks an incomplete B2B schedule before the request reaches the API', () => {
    const terms = {
      ...createDefaultBusinessDocumentTerms(),
      contract_scenario: 'supply' as const,
      payment_schedule: [{ share_percent: 60, due_event: 'before_supply' as const, due_days: null, due_day_kind: 'banking' as const, note: null }],
    };

    expect(businessTermsValidationError('contract', terms))
      .toBe('График оплаты должен составлять ровно 100%');
  });

  it('uses zero as an explicit no-contractual-warranty choice', () => {
    const terms = {
      ...createDefaultBusinessDocumentTerms(),
      contract_scenario: 'supply' as const,
      goods_warranty_months: 0,
    };

    expect(businessTermsValidationError('contract', terms)).toBe('');
  });
});
