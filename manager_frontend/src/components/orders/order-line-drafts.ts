import { nextTick } from 'vue';

type Editable = { link_id?: number | null; editor?: { original: unknown | null; group?: number } };
// Only committed values participate in autosave, totals and document previews.
// An open editor may freely change its working copy without publishing partial input.
export const committedLines = <T extends Editable>(lines: T[]): T[] => lines.flatMap(line =>
  line.editor ? (line.editor.original ? [line.editor.original as T] : []) : [line]);

export const hasLineEdits = (lines: Array<Editable & { product_query?: string; title?: string; price?: number; cost?: number; client_description?: string | null; description?: string | null }>) => lines.some(line => {
  if (!line.editor) return false;
  const { editor, ...working } = line;
  return editor.original ? JSON.stringify(working) !== JSON.stringify(editor.original)
    : Boolean(line.product_query?.trim() || line.title?.trim() || line.price || line.cost || line.client_description?.trim() || line.description?.trim());
});

export const beginLineEdit = <T extends Editable>(line: T) => {
  if (!line.editor) line.editor = { original: JSON.parse(JSON.stringify(line)) };
};
export const commitLineEdit = (line: Editable, lines: Editable[] = [line]) => {
  const group = line.editor?.group;
  for (const target of lines) if (target === line || (group != null && target.editor?.group === group)) delete target.editor;
};
export const cancelLineEdit = <T extends Editable>(lines: T[], line: T) => {
  if (!line.editor) return;
  const group = line.editor.group;
  if (group != null) {
    for (const target of [...lines]) {
      if (target.editor?.group !== group) continue;
      delete target.editor.group;
      cancelLineEdit(lines, target);
    }
    return;
  }
  const original = line.editor.original;
  if (original) {
    const linkId = line.link_id ?? (original as Editable).link_id;
    Object.keys(line).forEach(key => { delete (line as Record<string, unknown>)[key]; });
    Object.assign(line, original, { link_id: linkId });
  } else {
    const index = lines.indexOf(line);
    if (index >= 0) lines.splice(index, 1);
  }
};

const keys = new WeakMap<object, number>();
let sequence = 0;
export const lineKey = (line: object) => {
  if (!keys.has(line)) keys.set(line, ++sequence);
  return keys.get(line)!;
};

export async function focusLineEditor(row: HTMLElement | null | undefined) {
  await nextTick();
  const field = row?.querySelector<HTMLTextAreaElement>('textarea');
  if (!field) return;
  field.focus({ preventScroll: true });
  // Scroll only this order's workspace, never the page or a neighbouring card.
  const container = field.closest<HTMLElement>('[data-order-scroll]');
  if (container) {
    const top = row!.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
    container.scrollTo({ top: Math.max(0, top - 12), behavior: 'instant' });
  }
}

export const lineErrors = (line: { product_id?: number; quantity: number; price: number; cost: number }, title: string, product = false) => {
  const errors: Record<string, string> = {};
  if (!title.trim()) errors.title = 'Укажите название';
  else if (product && !line.product_id && title.trim().length > 1000) errors.title = 'Не более 1000 символов';
  if (!Number.isInteger(line.quantity) || line.quantity <= 0) errors.quantity = 'Целое число больше 0';
  const money = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value >= 0
    && (product ? Number.isSafeInteger(value) : Number.isSafeInteger(Math.round(value * 100)) && Math.abs(value * 100 - Math.round(value * 100)) < 1e-7);
  if (!money(line.price)) errors.price = product ? 'Целое число от 0' : 'Сумма от 0 с точностью до копейки';
  if (line.cost != null && (line.cost as unknown) !== '' && !money(line.cost)) errors.cost = product ? 'Целое число от 0' : 'Сумма от 0 с точностью до копейки';
  return errors;
};
