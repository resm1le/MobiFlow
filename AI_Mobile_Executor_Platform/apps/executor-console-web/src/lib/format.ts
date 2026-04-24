export function formatDateTime(
  value: string | number | null | undefined,
  locale?: string,
): string {
  if (value === null || value === undefined || value === 0) {
    return "N/A";
  }

  const rawValue = String(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return rawValue;
  }

  return date.toLocaleString(locale);
}

export function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function parseJsonInput(input: string): Record<string, unknown> {
  const parsed = JSON.parse(input);
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("JSON must be an object.");
  }
  return parsed as Record<string, unknown>;
}
