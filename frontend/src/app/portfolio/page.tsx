"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { RefreshCw, Plus } from "lucide-react";
import { api } from "@/lib/api";
import type { PortfolioSummary, Trade, ValueTimelinePoint } from "@/lib/types";

import { PortfolioSummary as PortfolioSummaryCard } from "@/components/portfolio/portfolio-summary";
import { AllocationDonut } from "@/components/portfolio/allocation-donut";
import { HoldingsTable } from "@/components/portfolio/holdings-table";
import { PriceChartCard } from "@/components/portfolio/price-chart-card";
import { WatchlistCard } from "@/components/portfolio/watchlist-card";
import { TradeDialog } from "@/components/portfolio/trade-dialog";
import { ShareToggle } from "@/components/portfolio/share-toggle";
import { PortfolioTimelineCard } from "@/components/portfolio/portfolio-timeline-card";
import { TransactionHistoryTable } from "@/components/portfolio/transaction-history-table";
import { SymbolChartDialog } from "@/components/portfolio/symbol-chart-dialog";
import { SaxoSection } from "@/components/saxo-section";
import { SaxoReconnectBanner } from "@/components/saxo-reconnect-banner";
import { useVisibleInterval } from "@/hooks/use-visible-interval";

export default function PortfolioPage() {
  const [p, setP] = useState<PortfolioSummary | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [timeline, setTimeline] = useState<ValueTimelinePoint[]>([]);
  const [livePrices, setLivePrices] = useState<Record<string, { price: number; change: number; change_pct: number }>>({});
  const [flashes, setFlashes] = useState<Record<string, "up" | "down">>({});
  const prevPricesRef = useRef<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [showTrade, setShowTrade] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tradeChartSymbol, setTradeChartSymbol] = useState<string | null>(null);

  // Auto-update: portfolio (with fresh staleness/warnings) + live prices,
  // every 30s, only while the tab is visible. `live` drives the LivePill.
  const refresh = useCallback(async () => {
    try {
      const [port, lp] = await Promise.all([api.portfolio(), api.livePrices()]);
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
    } finally {
      setLoading(false);
    }
  }, []);
  const live = useVisibleInterval(refresh, 30000);

  const reloadTradesAndTimeline = useCallback(() => {
    api.trades().then(setTrades).catch(() => {});
    api.portfolioValueTimeline().then(setTimeline).catch(() => {});
  }, []);
  useEffect(() => { reloadTradesAndTimeline(); }, [reloadTradesAndTimeline]);

  const onMutated = () => { refresh(); reloadTradesAndTimeline(); };

  // Day P&L: live change per position summed in CHF, using each position's
  // own implied FX rate (market_value / native price) rather than re-deriving it.
  const dayTotals = useMemo(() => {
    if (!p) return { dayPnl: 0, dayPnlPct: 0 };
    let dayChangeChf = 0;
    let stockValueAtOpen = 0;
    for (const pos of p.positions) {
      const live = livePrices[pos.symbol];
      const refPrice = pos.last_price || pos.avg_cost_price || 0;
      const fx = refPrice && pos.quantity ? pos.market_value / (refPrice * pos.quantity) : 1;
      const livePrice = live?.price ?? pos.last_price ?? pos.avg_cost_price ?? 0;
      const changePerShare = live?.change ?? 0;
      dayChangeChf += changePerShare * pos.quantity * fx;
      stockValueAtOpen += (livePrice - changePerShare) * pos.quantity * fx;
    }
    return { dayPnl: dayChangeChf, dayPnlPct: stockValueAtOpen > 0 ? (dayChangeChf / stockValueAtOpen) * 100 : 0 };
  }, [p, livePrices]);

  const liveTotalValue = useMemo(() => {
    if (!p) return 0;
    let value = p.cash_balance ?? 0;
    for (const pos of p.positions) {
      const live = livePrices[pos.symbol];
      const refPrice = pos.last_price || pos.avg_cost_price || 0;
      const fx = refPrice && pos.quantity ? pos.market_value / (refPrice * pos.quantity) : 1;
      const livePrice = live?.price ?? pos.last_price ?? pos.avg_cost_price ?? 0;
      value += livePrice * pos.quantity * fx;
    }
    return value;
  }, [p, livePrices]);

  // Money-weighted P&L needs recorded deposits; without them the subtraction
  // degenerates to the raw portfolio value. Fall back to cost-basis P&L in
  // that case and label the chip honestly.
  const netDeposits = p?.net_deposits ?? 0;
  const totalCost = p?.total_cost ?? 0;
  const allTime =
    netDeposits > 0
      ? { pnl: liveTotalValue - netDeposits, pct: ((liveTotalValue - netDeposits) / netDeposits) * 100, label: "all-time P&L" }
      : { pnl: liveTotalValue - totalCost, pct: totalCost > 0 ? ((liveTotalValue - totalCost) / totalCost) * 100 : 0, label: "unrealized P&L" };

  if (loading && !p) return <div className="space-y-6">{[...Array(4)].map((_, i) => <div key={i} className="h-32 rounded-3xl bg-muted animate-pulse" />)}</div>;

  return (
    <div className="space-y-8">
      <style>{`
        @keyframes flash-up { 0% { background-color: rgba(34,197,94,0.25); } 100% { background-color: transparent; } }
        @keyframes flash-down { 0% { background-color: rgba(239,68,68,0.25); } 100% { background-color: transparent; } }
        .flash-up { animation: flash-up 1.5s ease-out; }
        .flash-down { animation: flash-down 1.5s ease-out; }
      `}</style>

      <PortfolioSummaryCard
        totalValue={liveTotalValue}
        totalCost={p?.total_cost ?? 0}
        cashBalance={p?.cash_balance ?? 0}
        positionsCount={p?.positions_count ?? 0}
        dayPnl={dayTotals.dayPnl}
        dayPnlPct={dayTotals.dayPnlPct}
        allTimePnl={allTime.pnl}
        allTimePnlPct={allTime.pct}
        allTimeLabel={allTime.label}
        positions={p?.positions ?? []}
        warnings={p?.warnings ?? []}
        live={live}
        actions={
          <>
            <ShareToggle />
            <button onClick={refresh} disabled={loading} className="h-10 w-10 rounded-xl bg-muted flex items-center justify-center hover:bg-muted/80 transition-colors cursor-pointer"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
            <Button onClick={() => setShowTrade(true)} className="rounded-[14px] h-auto px-5 py-3 text-[14px] font-semibold" style={{ boxShadow: "0 10px 24px -10px rgba(59,130,246,0.4)" }}><Plus className="h-4 w-4 mr-1.5" />New Trade</Button>
          </>
        }
      />

      <div className="grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-5">
        <AllocationDonut positions={p?.positions ?? []} />
        <HoldingsTable
          positions={p?.positions ?? []}
          livePrices={livePrices}
          flashes={flashes}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={setSelectedSymbol}
          onChanged={onMutated}
        />
        <PriceChartCard symbol={selectedSymbol} positions={p?.positions ?? []} livePrices={livePrices} fetchChart={(t, r) => api.priceChart(t, r).then((res) => res.data)} />
      </div>

      <WatchlistCard />

      <PortfolioTimelineCard timeline={timeline} />

      <TransactionHistoryTable trades={trades} onOpenChart={setTradeChartSymbol} />
      <SaxoReconnectBanner />
      <SaxoSection />

      <SymbolChartDialog symbol={tradeChartSymbol} onClose={() => setTradeChartSymbol(null)} fetchChart={(t, r) => api.priceChart(t, r).then((res) => res.data)} />
      <TradeDialog open={showTrade} onOpenChange={setShowTrade} onSuccess={onMutated} />
    </div>
  );
}
