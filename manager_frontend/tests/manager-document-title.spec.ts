import { computed, effectScope, ref, type EffectScope, type Ref } from 'vue';
import { afterEach, describe, expect, it } from 'vitest';
import { useManagerDocumentTitle } from '../src/services/manager-document-title';

const scopes: EffectScope[] = [];
const registerTitle = (title: Readonly<Ref<string | null | undefined>>, role: 'identity' | 'page' = 'page') => {
  const scope = effectScope();
  scopes.push(scope);
  scope.run(() => useManagerDocumentTitle(title, role));
  return scope;
};

afterEach(() => { scopes.splice(0).reverse().forEach(scope => scope.stop()); });

describe('shared Manager document title owner', () => {
  it('uses identity until a page claims the title and ignores late identity responses while the page is open', async () => {
    const identity = ref<string | null>('Первоначальный бренд');
    registerTitle(identity, 'identity');
    expect(document.title).toBe('Первоначальный бренд · KitLane');

    const orderId = ref(477);
    const customer = ref('Клиент');
    registerTitle(computed(() => `Заказ №${orderId.value} · ${customer.value}`));
    expect(document.title).toBe('Заказ №477 · Клиент · KitLane');

    // The brand request can finish after the order has already rendered.
    await Promise.resolve().then(() => { identity.value = 'Загруженный бренд'; });
    expect(document.title).toBe('Заказ №477 · Клиент · KitLane');

    customer.value = 'Новое имя клиента';
    expect(document.title).toBe('Заказ №477 · Новое имя клиента · KitLane');
    orderId.value = 478;
    expect(document.title).toBe('Заказ №478 · Новое имя клиента · KitLane');
  });

  it('restores the current identity on page disposal and the default on identity disposal', () => {
    const identity = ref('MVN');
    const identityScope = registerTitle(identity, 'identity');
    const pageScope = registerTitle(ref('Заказ №477 · Клиент'));
    identity.value = 'Обновлённый бренд';
    pageScope.stop();
    expect(document.title).toBe('Обновлённый бренд · KitLane');
    identityScope.stop();
    expect(document.title).toBe('KitLane');
  });

  it('restores the default after leaving a page without an available identity', () => {
    registerTitle(ref(null), 'identity');
    const pageScope = registerTitle(ref('Заказ №477'));
    expect(document.title).toBe('Заказ №477 · KitLane');
    pageScope.stop();
    expect(document.title).toBe('KitLane');
  });

  it('keeps a newer page title when the old page scope is disposed', () => {
    const previousPage = registerTitle(ref('Заказ №477'));
    const nextPage = registerTitle(ref('Заказ №478'));
    previousPage.stop();
    expect(document.title).toBe('Заказ №478 · KitLane');
    nextPage.stop();
    expect(document.title).toBe('KitLane');
  });
});
