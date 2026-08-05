const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

export function bytes(value: number | null | undefined, digits = 1): string {
  if (!value || value < 0) return "—";
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < BYTE_UNITS.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : digits)} ${BYTE_UNITS[unit]}`;
}

export function speed(bytesPerSecond: number | null | undefined): string {
  if (!bytesPerSecond) return "—";
  return `${bytes(bytesPerSecond)}/s`;
}

export function duration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0) return "—";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function longDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const hours = Math.round(seconds / 3600);
  if (hours < 48) return `${hours} hours`;
  return `${Math.round(hours / 24)} days`;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return `${value.toFixed(0)}%`;
}

export function padNumber(value: number, total: number): string {
  const width = Math.max(3, String(Math.max(total, 1)).length);
  return String(value).padStart(width, "0");
}
