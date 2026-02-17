function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

export function toLocalDateTimeInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const year = date.getFullYear();
  const month = pad2(date.getMonth() + 1);
  const day = pad2(date.getDate());
  const hours = pad2(date.getHours());
  const minutes = pad2(date.getMinutes());

  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

export function fromLocalDateTimeInput(local: string | null | undefined): string | null {
  if (!local) return null;
  const normalized = local.trim();
  if (!normalized) return null;

  // Keep datetime timezone-naive for backend fields stored as TIMESTAMP WITHOUT TIME ZONE.
  // Browser datetime-local value is already in `YYYY-MM-DDTHH:mm` local form.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`;
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(normalized)) {
    return normalized;
  }
  return null;
}
