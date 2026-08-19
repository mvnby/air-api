import type { ProductCollectionRuleConfig } from '../../client';

export const sanitizeProductCollectionRuleConfig = (
  ruleConfig: ProductCollectionRuleConfig,
  canManagePlatform: boolean,
): ProductCollectionRuleConfig => {
  if (canManagePlatform) {
    return {
      ...ruleConfig,
      public_stock_states: [...(ruleConfig.public_stock_states || [])],
    };
  }
  const { public_stock_states: _internalStockStates, ...safeRuleConfig } = ruleConfig;
  return safeRuleConfig;
};
