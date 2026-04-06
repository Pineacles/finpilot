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
