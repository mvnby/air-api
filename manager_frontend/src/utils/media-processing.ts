export type BackgroundRemovalProvider = 'auto' | 'noop' | 'manual' | 'rembg' | 'birefnet' | 'ben';

export const backgroundRemovalProviderOptions: Array<{
  value: BackgroundRemovalProvider;
  label: string;
}> = [
  { value: 'auto', label: 'auto' },
  { value: 'noop', label: 'noop' },
  { value: 'manual', label: 'manual' },
  { value: 'rembg', label: 'rembg' },
  { value: 'birefnet', label: 'BiRefNet' },
  { value: 'ben', label: 'BEN' },
];
