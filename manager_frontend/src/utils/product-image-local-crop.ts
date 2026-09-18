import { OpenAPI } from '../client';
import type { ApiRequestOptions } from '../client/core/ApiRequestOptions';

export type ProductImageCropRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ProductImageCropSize = {
  width: number;
  height: number;
};

export type LocalCroppedProductImage = {
  id: number;
  url: string;
};

export const LOCAL_CROP_MAX_DIMENSION = 8_192;
export const LOCAL_CROP_MAX_PIXELS = 32_000_000;
export const LOCAL_CROP_SLOW_PIXELS = 12_000_000;

export const localCropWorkflowAvailability = {
  crop: true,
  rotate: true,
  backgroundRemoval: false,
  backgroundRemovalReason: 'Удаление фона требует отдельной серверной обработки и недоступно в локальном редакторе.',
} as const;

const hasCanvasSupport = () => {
  if (typeof document === 'undefined') return false;
  const canvas = document.createElement('canvas');
  return Boolean(canvas.getContext('2d') && typeof canvas.toBlob === 'function');
};

export const getLocalCropCapabilityError = (): string | null => {
  if (typeof fetch !== 'function' || typeof createImageBitmap !== 'function' || !hasCanvasSupport()) {
    return 'Этот браузер не умеет безопасно подготовить изображение локально. Обновите браузер и повторите.';
  }
  return null;
};

export const assessLocalCropSize = (size: ProductImageCropSize): { error: string | null; warning: string | null } => {
  const width = Math.trunc(size.width);
  const height = Math.trunc(size.height);
  if (width < 1 || height < 1) {
    return { error: 'У изображения нет читаемых размеров.', warning: null };
  }
  const pixels = width * height;
  if (width > LOCAL_CROP_MAX_DIMENSION || height > LOCAL_CROP_MAX_DIMENSION || pixels > LOCAL_CROP_MAX_PIXELS) {
    return {
      error: `Изображение ${width}×${height} слишком большое для безопасной обработки в браузере. Уменьшите его до ${LOCAL_CROP_MAX_DIMENSION}px по стороне и ${Math.floor(LOCAL_CROP_MAX_PIXELS / 1_000_000)} Мп.`,
      warning: null,
    };
  }
  if (pixels > LOCAL_CROP_SLOW_PIXELS) {
    return { error: null, warning: 'Большое изображение: подготовка кадра может занять несколько секунд.' };
  }
  return { error: null, warning: null };
};

export const clampLocalCropRect = (
  rect: ProductImageCropRect,
  size: ProductImageCropSize,
): ProductImageCropRect => {
  const sourceWidth = Math.max(1, Math.trunc(size.width));
  const sourceHeight = Math.max(1, Math.trunc(size.height));
  const x = Math.max(0, Math.min(Math.trunc(rect.x), sourceWidth - 1));
  const y = Math.max(0, Math.min(Math.trunc(rect.y), sourceHeight - 1));
  return {
    x,
    y,
    width: Math.max(1, Math.min(Math.trunc(rect.width), sourceWidth - x)),
    height: Math.max(1, Math.min(Math.trunc(rect.height), sourceHeight - y)),
  };
};

export const localCropRotatedSize = (
  size: ProductImageCropSize,
  quarterTurns: number,
): ProductImageCropSize => (
  Math.abs(Math.trunc(quarterTurns)) % 2
    ? { width: size.height, height: size.width }
    : { width: size.width, height: size.height }
);

const canvasBlob = (canvas: HTMLCanvasElement): Promise<Blob> => new Promise((resolve, reject) => {
  canvas.toBlob((blob) => {
    if (blob) resolve(blob);
    else reject(new Error('Браузер не смог подготовить файл изображения.'));
  }, 'image/webp', 0.9);
});

const canvasForSize = (size: ProductImageCropSize): HTMLCanvasElement => {
  const assessment = assessLocalCropSize(size);
  if (assessment.error) throw new Error(assessment.error);
  const canvas = document.createElement('canvas');
  canvas.width = Math.trunc(size.width);
  canvas.height = Math.trunc(size.height);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Браузер не предоставил canvas для обработки изображения.');
  return canvas;
};

export const loadLocalCropSource = async (url: string): Promise<{ blob: Blob; bitmap: ImageBitmap; warning: string | null }> => {
  const capabilityError = getLocalCropCapabilityError();
  if (capabilityError) throw new Error(capabilityError);

  let response: Response;
  try {
    response = await fetch(url, { credentials: 'same-origin', mode: 'cors' });
  } catch {
    throw new Error('Не удалось получить исходное фото. Для внешнего адреса сервер должен разрешать CORS.');
  }
  if (!response.ok) throw new Error(`Не удалось получить исходное фото (HTTP ${response.status}).`);

  const blob = await response.blob();
  if (!blob.size) throw new Error('Исходное фото пустое.');
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(blob);
  } catch {
    throw new Error('Браузер не смог открыть исходное фото.');
  }
  const assessment = assessLocalCropSize({ width: bitmap.width, height: bitmap.height });
  if (assessment.error) {
    bitmap.close();
    throw new Error(assessment.error);
  }
  return { blob, bitmap, warning: assessment.warning };
};

export const renderLocalCropRotation = async (
  source: ImageBitmap,
  quarterTurns: number,
): Promise<{ blob: Blob; size: ProductImageCropSize }> => {
  const normalizedTurns = ((Math.trunc(quarterTurns) % 4) + 4) % 4;
  const size = localCropRotatedSize(source, normalizedTurns);
  const canvas = canvasForSize(size);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Браузер не предоставил canvas для обработки изображения.');
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate(normalizedTurns * (Math.PI / 2));
  context.drawImage(source, -source.width / 2, -source.height / 2);
  return { blob: await canvasBlob(canvas), size };
};

export const createLocalCroppedImageFile = async (
  source: Blob,
  crop: ProductImageCropRect,
): Promise<File> => {
  const bitmap = await createImageBitmap(source);
  try {
    const rect = clampLocalCropRect(crop, bitmap);
    const canvas = canvasForSize({ width: rect.width, height: rect.height });
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Браузер не предоставил canvas для обработки изображения.');
    context.drawImage(bitmap, rect.x, rect.y, rect.width, rect.height, 0, 0, rect.width, rect.height);
    const blob = await canvasBlob(canvas);
    return new File([blob], 'product-crop.webp', { type: blob.type || 'image/webp' });
  } finally {
    bitmap.close();
  }
};

const resolveToken = async (method: ApiRequestOptions['method'], url: string) => {
  if (typeof OpenAPI.TOKEN === 'function') return OpenAPI.TOKEN({ method, url });
  return OpenAPI.TOKEN;
};

const requestCroppedImageReplacement = async (imageId: number, file: File): Promise<LocalCroppedProductImage> => {
  const path = `/api/manager/gallery/${encodeURIComponent(String(imageId))}/replace-local`;
  const token = await resolveToken('POST', path);
  const body = new FormData();
  body.append('file', file, file.name);
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    method: 'POST',
    body,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string' ? detail : `Ошибка сохранения (${response.status})`;
    throw Object.assign(new Error(message), { body: payload, status: response.status, statusText: response.statusText });
  }
  return payload as LocalCroppedProductImage;
};

export const saveLocalCroppedProductImage = async (options: {
  productId: number;
  imageId: number;
  file: File;
  mode: 'append' | 'replace';
  isInstallation: boolean;
  upload: (productId: number, files: File[], isInstallation: boolean) => Promise<{ images: LocalCroppedProductImage[] }>;
}): Promise<LocalCroppedProductImage> => {
  if (options.mode === 'replace') return requestCroppedImageReplacement(options.imageId, options.file);
  const result = await options.upload(options.productId, [options.file], options.isInstallation);
  const image = result.images[0];
  if (!image) throw new Error('Сервер не вернул добавленное изображение.');
  return image;
};
