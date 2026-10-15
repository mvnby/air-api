import type { EnvelopePrintPayload } from '../../client';

export type EnvelopeFormat = NonNullable<EnvelopePrintPayload['format']>;

// Physical page sizes, in landscape orientation, also used by the PDF renderer.
export const envelopeFormats = {
  DL: { width: 220, height: 110, description: 'A4, сложенный втрое' },
  C6: { width: 162, height: 114, description: 'A4, сложенный вчетверо' },
  C5: { width: 229, height: 162, description: 'A4, сложенный пополам' },
  C4: { width: 324, height: 229, description: 'A4 без сгибов' },
} satisfies Record<EnvelopeFormat, { width: number; height: number; description: string }>;
