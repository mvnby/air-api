export const legalEntityTypeForName = (displayName: string): 'individual_entrepreneur' | 'organization' => (
  /^(ип(?:\s|$)|индивидуальный предприниматель)/i.test(displayName.trim())
    ? 'individual_entrepreneur'
    : 'organization'
);
