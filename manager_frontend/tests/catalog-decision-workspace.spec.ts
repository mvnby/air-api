import { describe, expect, it } from 'vitest';

import { MANAGER_CAPABILITY, requiredCapabilityForManagerPath } from '../src/manager-capabilities';

describe('catalog decision workspace boundary', () => {
  it('keeps the supplier-aware system workspace out of tenant navigation', () => {
    expect(requiredCapabilityForManagerPath('/manager/catalog-decision'))
      .toBe(MANAGER_CAPABILITY.platformManage);
  });
});
