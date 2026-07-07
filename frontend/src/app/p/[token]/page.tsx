"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Sun, Moon } from "lucide-react";
import { api } from "@/lib/api";
import type { PublicPortfolio, Trade, ValueTimelinePoint } from "@/lib/types";

import { PortfolioSummary as PortfolioSummaryCard } from "@/components/portfolio/portfolio-summary";
import { AllocationDonut } from "@/components/portfolio/allocation-donut";
import { HoldingsTable } from "@/components/portfolio/holdings-table";
import { PriceChartCard } from "@/components/portfolio/price-chart-card";
import { PortfolioTimelineCard } from "@/components/portfolio/portfolio-timeline-card";
import { TransactionHistoryTable } from "@/components/portfolio/transaction-history-table";
import { SymbolChartDialog } from "@/components/portfolio/symbol-chart-dialog";
import { useVisibleInterval } from "@/hooks/use-visible-interval";

export default function PublicPortfolioPage() {
  const { token } = useParams<{ token: string }>();
  const [p, setP] = useState<PublicPortfolio | null>(null);
  const [error, setError] = useState(false);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [timeline, setTimeline] = useState<ValueTimelinePoint[]>([]);
  const [livePrices, setLivePrices] = useState<Record<string, { price: number; change: number; change_pct: number }>>({});
  const [flashes, setFlashes] = useState<Record<string, "up" | "down">>({});
  const prevPricesRef = useRef<Record<string, number>>({});
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tradeChartSymbol, setTradeChartSymbol] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.publicTrades(token).then(setTrades).catch(() => {});
    api.publicValueTimeline(token).then(setTimeline).catch(() => {});
  }, [token]);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const [port, lp] = await Promise.all([api.publicPortfolio(token), api.publicLivePrices(token)]);
      setP(port);
      const newFlashes: Record<string, "up" | "down"> = {};
      Object.entries(lp).forEach(([sym, price]) => {
        const old = prevPricesRef.current[sym];
        if (old !== undefined && price.price !== old) newFlashes[sym] = price.price > old ? "up" : "down";
        prevPricesRef.current[sym] = price.price;
      });
      setLivePrices(lp);
      if (Object.keys(newFlashes).length) {
        setFlashes(newFlashes);
        setTimeout(() => setFlashes({}), 1500);
      }
      setSelectedSymbol((cur) => cur ?? port.positions[0]?.symbol ?? null);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token]);
  const live = useVisibleInterval(refresh, 30000);

  const dayTotals = useMemo(() => {
    if (!p) return { dayPnl: 0, dayPnlPct: 0 };
    let dayChangeChf = 0;
    let stockValueAtOpen = 0;
    for (const pos of p.positions) {
      const lv = livePrices[pos.symbol];
      const refPrice = pos.last_price || pos.avg_cost_price || 0;
      const fx = refPrice && pos.quantity ? pos.market_value / (refPrice * pos.quantity) : 1;
      const livePrice = lv?.price ?? pos.last_price ?? pos.avg_cost_price ?? 0;
      const changePerShare = lv?.change ?? 0;
      dayChangeChf += changePerShare * pos.quantity * fx;
      stockValueAtOpen += (livePrice - changePerShare) * pos.quantity * fx;
    }
    return { dayPnl: dayChangeChf, dayPnlPct: stockValueAtOpen > 0 ? (dayChangeChf / stockValueAtOpen) * 100 : 0 };
  }, [p, livePrices]);

  const liveTotalValue = useMemo(() => {
    if (!p) return 0;
    let value = p.cash_balance ?? 0;
    for (const pos of p.positions) {
      const lv = livePrices[pos.symbol];
      const refPrice = pos.last_price || pos.avg_cost_price || 0;
      const fx = refPrice && pos.quantity ? pos.market_value / (refPrice * pos.quantity) : 1;
      const livePrice = lv?.price ?? pos.last_price ?? pos.avg_cost_price ?? 0;
      value += livePrice * pos.quantity * fx;
    }
    return value;
  }, [p, livePrices]);

  const [dark, setDark] = useState(false);
  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const isDark = stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  if (loading) return <div className="mx-auto max-w-7xl px-6 py-10 space-y-6">{[...Array(4)].map((_, i) => <div key={i} className="h-32 rounded-[24px] bg-muted animate-pulse" />)}</div>;

  if (error || !p) return (
    <div className="min-h-screen flex items-center justify-center">
      <button onClick={toggleTheme} className="glass fixed top-6 right-6 w-[42px] h-[42px] rounded-[14px] flex items-center justify-center text-foreground hover:brightness-110 transition-all cursor-pointer" aria-label="Toggle theme">{dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}</button>
      <div className="text-center">
        <h1 className="text-[24px] font-bold mb-2">Portfolio not found</h1>
        <p className="text-muted-foreground">This link may have expired or the portfolio is no longer public.</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <button onClick={toggleTheme} className="glass fixed top-6 right-6 w-[42px] h-[42px] rounded-[14px] flex items-center justify-center text-foreground hover:brightness-110 transition-all cursor-pointer z-50" aria-label="Toggle theme">{dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}</button>
      <div className="mx-auto max-w-7xl px-6 py-10 space-y-8">
        <style>{`
          @keyframes flash-up { 0% { background-color: rgba(34,197,94,0.25); } 100% { background-color: transparent; } }
          @keyframes flash-down { 0% { background-color: rgba(239,68,68,0.25); } 100% { background-color: transparent; } }
          .flash-up { animation: flash-up 1.5s ease-out; }
          .flash-down { animation: flash-down 1.5s ease-out; }
        `}</style>

        <div className="flex items-center gap-4 pb-2 border-b border-border/60">
          <div className="w-[52px] h-[52px] rounded-[14px] flex items-center justify-center shrink-0" style={{ background: "linear-gradient(135deg,#3b82f6 0%,#8b5cf6 100%)" }}>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" /></svg>
          </div>
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-[13px] font-bold tracking-tight" style={{ background: "linear-gradient(135deg,#3b82f6,#8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>FinPilot</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">Read-only view</span>
            </div>
            <p className="text-[15px] font-semibold text-foreground">Shared by {p.display_name}</p>
          </div>
        </div>

        <PortfolioSummaryCard
          totalValue={liveTotalValue}
          totalCost={p.total_cost}
          cashBalance={p.cash_balance}
          positionsCount={p.positions_count}
          dayPnl={dayTotals.dayPnl}
          dayPnlPct={dayTotals.dayPnlPct}
          allTimePnl={liveTotalValue - p.total_cost}
          allTimePnlPct={p.total_cost > 0 ? ((liveTotalValue - p.total_cost) / p.total_cost) * 100 : 0}
          allTimeLabel="all time"
          positions={p.positions}
          warnings={p.warnings}
          live={live}
        />

        <div className="grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-5">
          <AllocationDonut positions={p.positions} />
          <HoldingsTable positions={p.positions} livePrices={livePrices} flashes={flashes} selectedSymbol={selectedSymbol} onSelectSymbol={setSelectedSymbol} readOnly />
          <PriceChartCard symbol={selectedSymbol} positions={p.positions} livePrices={livePrices} fetchChart={(t, r) => api.publicChart(token, t, r).then((res) => res.data)} />
        </div>

        <PortfolioTimelineCard timeline={timeline} />
        <TransactionHistoryTable trades={trades} onOpenChart={setTradeChartSymbol} />
        <SymbolChartDialog symbol={tradeChartSymbol} onClose={() => setTradeChartSymbol(null)} fetchChart={(t, r) => api.publicChart(token, t, r).then((res) => res.data)} />

        <p className="text-center text-[12px] text-muted-foreground pt-4 pb-8">Shared via FinPilot</p>
      </div>
    </div>
  );
}
