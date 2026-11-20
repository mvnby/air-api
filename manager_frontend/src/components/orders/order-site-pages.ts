const ORDER_SITE_PAGE_SIZE = 100;

export async function loadOrderSitePages<T>(
  load: (limit: number, offset: number) => PromiseLike<{ items: T[]; total: number }>,
): Promise<T[]> {
  const items: T[] = [];
  while (true) {
    const page = await load(ORDER_SITE_PAGE_SIZE, items.length);
    items.push(...page.items);
    if (items.length >= page.total || page.items.length === 0) return items;
  }
}
