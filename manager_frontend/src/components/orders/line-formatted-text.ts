export interface LineTextRun { text: string; bold: boolean; italic: boolean }

// Only emphasis is interpreted; Vue renders every text segment with escaping.
export function parseLineText(value: string, bold = false, italic = false): LineTextRun[] {
  const pattern = /(?<!\*)(\*\*\*|\*\*|\*)(?!\*)(?=\S)(.+?)(?<=\S)\1(?!\*)/gs;
  const runs: LineTextRun[] = [];
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const start = match.index!;
    if (start > cursor) runs.push({ text: value.slice(cursor, start), bold, italic });
    const marker = match[1]!;
    runs.push(...parseLineText(match[2]!, bold || marker.length >= 2, italic || marker.length === 1 || marker.length === 3));
    cursor = start + match[0].length;
  }
  if (cursor < value.length) runs.push({ text: value.slice(cursor), bold, italic });
  return runs;
}
