import { describe, expect, it } from 'vitest';
import { legalEntityTypeForName } from '../src/features/settings/legal-entity-type';

describe('legalEntityTypeForName', () => {
  it('recognizes Cyrillic ИП names', () => {
    expect(legalEntityTypeForName('ИП Иванов')).toBe('individual_entrepreneur');
  });
});
