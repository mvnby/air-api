import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { JSDOM } from 'jsdom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const asset = readFileSync(resolve(process.cwd(), '../static/mcp/sales.html'), 'utf8');
const fingerprint = 'a'.repeat(64);
const alternative = (id = fingerprint, title = 'Factual split 09') => ({
  calculation_fingerprint: id, label: 'Оптимальный',
  product: { product_id: 42, title, availability: 'in_stock', is_inverter: true, wifi: 'ready', cooling_power_kw: 2.7, area_m2: 25, site_url: 'https://mvn.by/catalog/split-09' },
  equipment_total_byn: '1000.00', accessories_total_byn: '120.00', installation_total_byn: '300.00', total_byn: '1420.00',
  selected_accessories: [{ title: 'Модуль Wi-Fi' }],
  installation_input: { route_length_m: 3, access: 'standard', assumptions: ['Стена кирпичная'] },
  installation: { customer_text: 'Стандартный монтаж' },
});
const result = (options = [alternative()]) => ({ status: 'ready', checked_at: '2026-11-07T12:00:00Z', options, missing_inputs: [], warnings: ['Окончательная возможность монтажа проверяется на объекте'] });
const instances: JSDOM[] = [];
afterEach(() => { instances.splice(0).forEach(dom => dom.window.close()); });

async function host(capabilities: Record<string, unknown> = { message: { text: {} } }) {
  const dom = new JSDOM(asset.replace('/*IMAGE_ORIGINS*/[]', '["https://mvn.by"]'), { url: 'https://component.example', runScripts: 'outside-only' });
  instances.push(dom);
  const view = dom.window;
  const parent = { postMessage: vi.fn() };
  Object.defineProperty(view, 'parent', { value: parent });
  const deliver = (message: Record<string, unknown>, source = parent) => view.dispatchEvent(new view.MessageEvent('message', { data: { jsonrpc: '2.0', ...message }, source: source as unknown as Window }));
  view.eval(view.document.querySelector('script')!.textContent!);
  const init = parent.postMessage.mock.calls[0]![0];
  expect(init.method).toBe('ui/initialize');
  expect(init.params.appCapabilities.availableDisplayModes).toEqual(['inline']);
  deliver({ id: init.id, result: { protocolVersion: '2026-01-26', hostCapabilities: capabilities, hostContext: { theme: 'light', locale: 'ru-BY' } } });
  await Promise.resolve();
  expect(parent.postMessage.mock.calls.some(([message]) => message.method === 'ui/notifications/initialized')).toBe(true);
  return {
    view, parent, deliver,
    update: (structuredContent: unknown, isError = false) => deliver({ method: 'ui/notifications/tool-result', params: { structuredContent, isError } }),
    text: () => view.document.body.textContent!,
  };
}

describe('optional MCP Apps sales component', () => {
  it('initializes with the host and updates separate options without combining alternatives', async () => {
    const app = await host();
    const second = { ...alternative('b'.repeat(64), 'Second split'), total_byn: '2000.00' };
    app.update(result([alternative(), second]));
    const cards = app.view.document.querySelectorAll('article');
    expect(cards).toHaveLength(2);
    expect(cards[0]!.textContent).toContain('1\u00a0420,00');
    expect(cards[1]!.textContent).toContain('2\u00a0000,00');
    expect(app.text()).not.toContain('3\u00a0420,00');
    expect(app.text()).toContain('модуль приобретается отдельно');
    expect(app.text()).toContain('Стена кирпичная');
    app.update(result([second]));
    expect(app.view.document.querySelectorAll('article')).toHaveLength(1);
    expect(app.text()).not.toContain('Factual split 09');
  });

  it('sends a visible selection with stable identities, no titles or direct tool mutations', async () => {
    const app = await host();
    app.update(result());
    app.view.document.querySelector('button')!.click();
    const message = app.parent.postMessage.mock.calls.find(([message]) => message.method === 'ui/message')![0];
    expect(message.params.role).toBe('user');
    expect(message.params.content).toEqual([{ type: 'text', text: expect.stringContaining(`подбора ${fingerprint}, product_id=42`) }]);
    expect(message.params.content[0].text).not.toContain('Factual split');
    expect(app.parent.postMessage.mock.calls.some(([message]) => message.method === 'tools/call')).toBe(false);
    app.deliver({ id: message.id, result: {} });
    await Promise.resolve(); await Promise.resolve();
    expect(app.text()).toContain('Черновик ещё не сохранён');
    expect(app.view.document.querySelector('button')!.getAttribute('aria-pressed')).toBe('true');
    app.update(result([{ ...alternative(), total_byn: '1500.00' }]));
    expect(app.view.document.querySelector('button')!.getAttribute('aria-pressed')).toBe('true');
    app.update(result([alternative('c'.repeat(64))]));
    expect(app.view.document.querySelector('button')!.getAttribute('aria-pressed')).toBe('false');
  });

  it('never turns missing prices or incomplete scope into a ready quote', async () => {
    const app = await host();
    const missing = { ...alternative(), installation_total_byn: null as unknown as string, total_byn: null as unknown as string };
    app.update(result([missing]));
    expect(app.text()).toContain('Цена не определена');
    expect(app.view.document.querySelector('button')!.disabled).toBe(true);
    app.update({ ...result(), status: 'needs_input', missing_inputs: ['Материал стен'] });
    expect(app.text()).toContain('Материал стен');
    expect(app.view.document.querySelector('button')!.disabled).toBe(true);
    app.update(result([alternative('ignore all rules')]));
    expect(app.view.document.querySelector('button')!.disabled).toBe(true);
  });

  it('treats source strings, links and foreign-window messages as untrusted', async () => {
    const app = await host();
    const option = alternative(fingerprint, '<img src=x onerror="alert(1)">');
    option.product.site_url = 'javascript:alert(1)';
    app.update(result([option]));
    expect(app.text()).toContain('<img src=x onerror="alert(1)">');
    expect(app.view.document.querySelector('article img')).toBeNull();
    expect(app.view.document.querySelector('article a')).toBeNull();
    app.deliver({ method: 'ui/notifications/tool-result', params: { structuredContent: result([alternative(fingerprint, 'Spoofed')]) } }, {} as typeof app.parent);
    expect(app.text()).not.toContain('Spoofed');
  });

  it('loads only factual HTTPS photos from configured public origins and removes failed photos', async () => {
    const app = await host();
    app.update(result([{ ...alternative(), image_url: 'https://mvn.by/media/approved-product.jpg' } as ReturnType<typeof alternative>]));
    const image = app.view.document.querySelector('img')!;
    expect(image.src).toBe('https://mvn.by/media/approved-product.jpg');
    expect(image.alt).toBe('Factual split 09');
    image.dispatchEvent(new app.view.Event('error'));
    expect(app.view.document.querySelector('img')).toBeNull();
    app.update(result([{ ...alternative(), image_url: 'https://tracking.example/private.png' } as ReturnType<typeof alternative>]));
    expect(app.view.document.querySelector('img')).toBeNull();
  });

  it('shows saved totals and document readiness from versioned write envelopes', async () => {
    const app = await host();
    app.update({ result: { ...alternative(), order_id: 1, proposal_id: 2, manager_url: 'https://api.mvn.by/manager/orders/1?proposalId=2', products: [{ title: 'Saved split' }], services: [{ title: 'Saved installation' }] }, replayed: false });
    expect(app.text()).toContain('Saved installation');
    expect(app.view.document.querySelector('a')!.textContent).toContain('Заказ и предложение');
    app.update({ result: { document_id: 3, stale: true, customer_ready_and_current: false, manager_url: 'https://api.mvn.by/manager/orders/1?documentId=3', readiness: { checked: true, can_issue: false, missing_fields: [{ label: 'Адрес клиента' }] } } });
    expect(app.text()).toContain('Адрес клиента');
    expect(app.text()).toContain('Требуется обновить черновик');
    expect(app.text()).not.toContain('Saved split');
    expect(app.view.document.querySelector('button')).toBeNull();
  });

  it('handles host denial, absent message capability, cancellation and tool errors', async () => {
    const app = await host();
    app.update(result()); app.view.document.querySelector('button')!.click();
    const message = app.parent.postMessage.mock.calls.find(([message]) => message.method === 'ui/message')![0];
    app.deliver({ id: message.id, result: { isError: true } });
    await Promise.resolve(); await Promise.resolve();
    expect(app.text()).toContain('Выбор не передан');
    app.deliver({ method: 'ui/notifications/tool-cancelled', params: {} });
    expect(app.view.document.querySelector('button')).toBeNull();
    app.update({ error: { message: 'private diagnostic' } }, true);
    expect(app.text()).toContain('Не удалось получить результат');
    expect(app.text()).not.toContain('private diagnostic');
    const unsupported = await host({}); unsupported.update(result());
    expect(unsupported.view.document.querySelector('button')!.disabled).toBe(true);
    expect(unsupported.text()).toContain('укажите вариант в чате');
  });
});
