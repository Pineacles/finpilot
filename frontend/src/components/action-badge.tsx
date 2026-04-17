interface ActionBadgeProps {
  action: string;
  className?: string;
}

const ACTION_COLORS: Record<string, { bg: string; text: string }> = {
  ADD:   { bg: "rgba(22,163,74,0.15)",   text: "#16a34a" },
  BUY:   { bg: "rgba(22,163,74,0.15)",   text: "#16a34a" },
  SELL:  { bg: "rgba(220,38,38,0.15)",   text: "#dc2626" },
  HOLD:  { bg: "rgba(59,130,246,0.15)",  text: "#3b82f6" },
  WATCH: { bg: "rgba(245,158,11,0.15)",  text: "#d97706" },
  AVOID: { bg: "rgba(220,38,38,0.15)",   text: "#dc2626" },
};

export function ActionBadge({ action, className = "" }: ActionBadgeProps) {
  const key = action.toUpperCase();
  const colors = ACTION_COLORS[key] ?? { bg: "rgba(107,114,128,0.15)", text: "#6b7280" };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-[8px] text-[11px] font-700 font-semibold tracking-wide ${className}`}
      style={{ background: colors.bg, color: colors.text }}
    >
      {action.toUpperCase()}
    </span>
  );
}
