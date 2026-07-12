"use client";

import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, X } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { LivePill } from "@/components/live-pill";
import { formatCurrency, formatRelativeTime } from "@/lib/format";
import type { Position } from "@/lib/types";

function PnlBadge({ value, pct }: { value: number; pct?: number }) {
  const pos = value >= 0;
  return (
    <span
      className={`text-[13px] px-2.5 py-1 rounded-xl font-medium inline-flex items-center gap-1 ${
        pos
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
          : "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"
      }`}
    >
      {pos ? "+" : ""}
      {formatCurrency(value)}
      {pct !== undefined && (
        <span className="opacity-70">
          ({pos ? "+" : ""}
          {pct.toFixed(1)}%)
        </span>
      )}
    </span>
  );
}

interface PortfolioSummaryProps {
  totalValue: number;
  totalCost: number;
  cashBalance: number;
  positionsCount: number;
  dayPnl: number;
  dayPnlPct: number;
  allTimePnl: number;
  allTimePnlPct: number;
  allTimeLabel?: string;
  positions: Position[];
  warnings: string[];
  live: boolean;
  actions?: React.ReactNode;
}

export function PortfolioSummary({
  totalValue, totalCost, cashBalance, positionsCount,
  dayPnl, dayPnlPct, allTimePnl, allTimePnlPct, allTimeLabel = "all-time P&L",
  positions, warnings, live, actions,
}: PortfolioSummaryProps) {
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  const warningsKey = warnings.join("|");
  const showWarnings = warnings.length > 0 && dismissedFor !== warningsKey;

  const { staleSymbols, mostRecentAt } = useMemo(() => {
    const stale = positions.filter((p) => p.price_stale).map((p) => p.symbol);
    const timestamps = positions.map((p) => p.last_price_at).filter(Boolean) as string[];
    const mostRecent = timestamps.length
      ? timestamps.reduce((a, b) => (new Date(a) > new Date(b) ? a : b))
      : null;
    return { staleSymbols: stale, mostRecentAt: mostRecent };
  }, [positions]);

  return (
    <div className="space-y-3">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-[12px] font-semibold text-muted-foreground uppercase tracking-[0.5px]">Total Value</p>
            <LivePill live={live} />
            {positions.length > 0 && (
              <span className="group relative inline-flex items-center">
                <span className="text-[11px] text-muted-foreground">
                  prices as of {formatRelativeTime(mostRecentAt)}
                </span>
                {staleSymbols.length > 0 && (
                  <>
                    <span className="ml-1.5 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 text-[10px] font-semibold cursor-help">
                      <AlertTriangle className="h-3 w-3" />
                      {staleSymbols.length} stale
                    </span>
                    <span className="pointer-events-none absolute left-0 top-full mt-1.5 z-20 hidden group-hover:block w-max max-w-[260px] rounded-lg bg-popover border border-border px-3 py-2 text-[11px] text-foreground shadow-lg">
                      Live refresh failed for: {staleSymbols.join(", ")}, showing last known price.
                    </span>
                  </>
                )}
              </span>
            )}
          </div>
          <p className="font-mono tabular-nums text-[42px] font-extrabold" style={{ letterSpacing: "-1.2px" }}>
            <AnimatedNumber value={totalValue} format={formatCurrency} />
          </p>
          <div className="flex items-center gap-3 mt-2">
            <PnlBadge value={allTimePnl} pct={allTimePnlPct} />
            <span className="text-[13px] text-muted-foreground">{allTimeLabel}</span>
          </div>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </motion.div>

      {showWarnings && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <div className="flex-1 space-y-1">
            {warnings.map((w, i) => (
              <p key={i} className="text-[12.5px] text-amber-800 dark:text-amber-300 leading-snug">{w}</p>
            ))}
          </div>
          <button
            onClick={() => setDismissedFor(warningsKey)}
            className="shrink-0 p-1 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-500/20 cursor-pointer"
            aria-label="Dismiss warnings"
          >
            <X className="h-3.5 w-3.5 text-amber-700 dark:text-amber-400" />
          </button>
        </div>
      )}

      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        {[
          { l: "Invested", v: totalCost, fmt: formatCurrency, pct: undefined as number | undefined },
          { l: "Cash", v: cashBalance, fmt: formatCurrency, pct: undefined },
          { l: "Positions", v: positionsCount, fmt: (n: number) => String(Math.round(n)), pct: undefined },
          { l: "Day P&L", v: dayPnl, fmt: formatCurrency, pct: dayPnlPct },
        ].map((item, i) => (
          <GlassCard key={item.l} delay={0.05 + i * 0.05} className="!rounded-[20px] !p-[18px]">
            <p className="text-[12px] text-muted-foreground mb-1.5 uppercase tracking-wider font-medium">{item.l}</p>
            <p className={`font-mono tabular-nums text-[20px] font-bold ${item.l === "Day P&L" ? (item.v >= 0 ? "text-gain" : "text-loss") : ""}`}>
              <AnimatedNumber value={item.v} format={item.fmt} />
            </p>
            {item.pct !== undefined && (
              <p className={`text-[12px] tabular-nums mt-0.5 ${item.pct >= 0 ? "text-gain" : "text-loss"}`}>
                {item.pct >= 0 ? "+" : ""}
                {item.pct.toFixed(2)}%
              </p>
            )}
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
