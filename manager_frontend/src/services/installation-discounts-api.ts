import {
  ManagerInstallationDiscountsService,
  type ManagerInstallationDiscountPolicyResponse,
  type ManagerInstallationDiscountProductResponse,
  type ManagerInstallationDiscountStatus,
} from '../client';

export type InstallationDiscountPolicy = ManagerInstallationDiscountPolicyResponse;
export type InstallationDiscountProduct = ManagerInstallationDiscountProductResponse;
export type InstallationDiscountStatus = ManagerInstallationDiscountStatus;

export const installationDiscountsApi = {
  list(limit = 50, page = 1, search?: string) {
    return ManagerInstallationDiscountsService.listManagerInstallationDiscountRules(
      search,
      page,
      limit,
    );
  },
  updatePolicy(policy: InstallationDiscountPolicy) {
    return ManagerInstallationDiscountsService.updateManagerInstallationDiscountPolicy(
      policy,
    );
  },
  searchProducts(query: string, limit = 12) {
    return ManagerInstallationDiscountsService.searchManagerInstallationDiscountProducts(
      query.trim(),
      limit,
    );
  },
  saveProductOverride(productId: number, discountAmount: number) {
    return ManagerInstallationDiscountsService.upsertManagerInstallationDiscountRule(
      productId,
      { discount_amount: discountAmount },
    );
  },
  deleteProductOverride(productId: number) {
    return ManagerInstallationDiscountsService.deleteManagerInstallationDiscountRule(
      productId,
    );
  },
};
