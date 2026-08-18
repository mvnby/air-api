const SYSTEM_ONLY_COMPONENT_FIELDS = [
  'supplier_id',
  'supplier_invoice_number',
  'supplier_invoice_date',
] as const;

export const sanitizeEquipmentComponentPayload = <T extends Record<string, unknown>>(
  payload: T,
  canManagePlatform: boolean,
): T => {
  if (canManagePlatform) return payload;
  const sanitized = { ...payload };
  for (const field of SYSTEM_ONLY_COMPONENT_FIELDS) delete sanitized[field];
  return sanitized;
};
