export function formatCurrency(amount: number, currency = "CHF"): string {
  return new Intl.NumberFormat("de-CH", { style: "currency", currency }).format(amount);
}

export function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("de-CH");
}

export function cn(...classes: (string | false | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}

/** "prices as of X": relative time for a nullable ISO timestamp. Returns
 * "unknown" rather than silently showing nothing when we have no timestamp
 * at all (e.g. a price that has never successfully been fetched). */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const diffMs = Date.now() - then;
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}
