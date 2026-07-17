const OPTIMIZABLE_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

export const CLIENT_IMAGE_MAX_DIMENSION = 2560;
export const CLIENT_IMAGE_MIN_OPTIMIZE_BYTES = 750 * 1024;
export const CLIENT_IMAGE_WEBP_QUALITY = 0.88;

export const shouldOptimizeImageUpload = (file: Pick<File, 'type' | 'size'>): boolean => (
  OPTIMIZABLE_IMAGE_TYPES.has(file.type.toLowerCase())
);

export const needsImageOptimization = (width: number, height: number, size: number): boolean => (
  Math.max(width, height) > CLIENT_IMAGE_MAX_DIMENSION
  || size >= CLIENT_IMAGE_MIN_OPTIMIZE_BYTES
);

export const optimizedImageFileName = (name: string): string => {
  const base = name.replace(/\.[^.]+$/, '') || 'image';
  return `${base}.webp`;
};

const canvasToBlob = (canvas: HTMLCanvasElement): Promise<Blob | null> => new Promise((resolve) => {
  canvas.toBlob(resolve, 'image/webp', CLIENT_IMAGE_WEBP_QUALITY);
});

export const optimizeImageForUpload = async (file: File): Promise<File> => {
  if (!shouldOptimizeImageUpload(file) || typeof createImageBitmap !== 'function') {
    return file;
  }

  try {
    const bitmap = await createImageBitmap(file);
    if (!needsImageOptimization(bitmap.width, bitmap.height, file.size)) {
      bitmap.close();
      return file;
    }
    const scale = Math.min(1, CLIENT_IMAGE_MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) {
      bitmap.close();
      return file;
    }
    context.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();

    const optimized = await canvasToBlob(canvas);
    if (!optimized || optimized.size >= file.size) {
      return file;
    }
    return new File([optimized], optimizedImageFileName(file.name), {
      type: 'image/webp',
      lastModified: file.lastModified,
    });
  } catch {
    // Uploading the original is safer than blocking the user on browser codec support.
    return file;
  }
};
