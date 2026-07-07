"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, TrendingUp, Loader2, ChevronRight } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { LivePill } from "@/components/live-pill";
import { formatCurrency, formatPct } from "@/lib/format";
import { api, PortfolioSummary } from "@/lib/api";
import { useVisibleInterval } from "@/hooks/use-visible-interval";

/** Total portfolio value + today's live change, linking through to the full
 * portfolio page. Not a TanStack Query hook — the portfolio page itself
 * isn't refactored this phase, so this widget polls independently, same
 * pattern the portfolio page already uses. */
export function PortfolioSnapshotWidget() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [livePrices, setLivePrices] = useState<Record<string, { price: number; change: number; change_pct: number }>>({});
  const [loading, setLoading] = useState(true);
  const loadedOnce = useRef(false);

  const poll = useCallback(async () => {
    try {
      const [port, lp] = await Promise.all([api.portfolio(), api.livePrices()]);
      setPortfolio(port);
      setLivePrices(lp);
    } catch {
      // keep last-known values on transient failure
    } finally {
      loadedOnce.current = true;
      setLoading(false);
    }
  }, []);
  const live = useVisibleInterval(poll, 15000);

  const totals = useMemo(() => {
    if (!portfolio) return { value: 0, dayPnl: 0, dayPnlPct: 0 };
    let stockValue = 0;
    let dayChangeChf = 0;
    let stockValueAtOpen = 0;
    for (const pos of portfolio.positions) {
      const lp = livePrices[pos.symbol];
      const refPrice = pos.last_price || pos.avg_cost_price || 0;
      const fx = refPrice && pos.quantity ? pos.market_value / (refPrice * pos.quantity) : 1;
      const livePrice = lp?.price ?? pos.last_price ?? pos.avg_cost_price ?? 0;
      const changePerShare = lp?.change ?? 0;
      stockValue += livePrice * pos.quantity * fx;
      dayChangeChf += changePerShare * pos.quantity * fx;
      stockValueAtOpen += (livePrice - changePerShare) * pos.quantity * fx;
    }
    const value = stockValue + (portfolio.cash_balance ?? 0);
    const dayPnlPct = stockValueAtOpen > 0 ? (dayChangeChf / stockValueAtOpen) * 100 : 0;
    return { value, dayPnl: dayChangeChf, dayPnlPct };
  }, [portfolio, livePrices]);

  const up = totals.dayPnl >= 0;

  return (
    <GlassCard className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute -top-10 -right-10 h-[140px] w-[140px] rounded-full opacity-35 blur-[40px]"
        style={{ background: "linear-gradient(135deg, #f59e0b, #ef4444)" }}
      />
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-5">
          <div className="h-[44px] w-[44px] rounded-[14px] bg-orange-100 dark:bg-orange-500/15 flex items-center justify-center">
            <TrendingUp className="h-6 w-6 text-orange-600 dark:text-orange-400" strokeWidth={1.8} />
          </div>
          <div className="flex items-center gap-2">
            <LivePill live={live} />
            <Link href="/portfolio" className="p-1.5 rounded-lg hover:bg-accent cursor-pointer transition-colors">
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </Link>
          </div>
        </div>
        <p className="text-[12px] font-medium text-muted-foreground mb-1">Portfolio</p>
        {loading && !loadedOnce.current ? (
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        ) : (
          <>
            <p className="font-mono tabular-nums text-[28px] font-bold" style={{ letterSpacing: "-0.8px" }}>
              <AnimatedNumber value={totals.value} format={formatCurrency} />
            </p>
            <p className={`text-[13px] font-semibold flex items-center gap-1 mt-2 ${up ? "text-gain" : "text-loss"}`}>
              {up ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {formatCurrency(Math.abs(totals.dayPnl))} ({formatPct(totals.dayPnlPct)}) today
            </p>
          </>
        )}
      </div>
    </GlassCard>
  );
}
