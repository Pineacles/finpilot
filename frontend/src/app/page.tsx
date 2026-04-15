"use client";

import { useEffect, useState, useRef, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { api, Overview, PortfolioSummary, MacroRegime, BlackSwanResult } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import {
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Landmark,
  CreditCard,
  TrendingUp,
  Banknote,
  Pencil,
  X,
  TrendingDown,
  Minus,
  Activity,
} from "lucide-react";

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-muted ${className ?? ""}`} />;
}

function GlassCard({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={`glass bg-card rounded-3xl p-6 ${className}`}
    >
      {children}
    </motion.div>
  );
}

function MetricCard({ icon: Icon, iconBg, iconColor, label, value, sub, delay, live, onEdit }: {
  icon: React.ElementType; iconBg: string; iconColor: string;
  label: string; value: React.ReactNode; sub?: React.ReactNode; delay: number; live?: boolean; onEdit?: () => void;
}) {
  return (
    <GlassCard delay={delay}>
      <div className="flex items-start justify-between mb-5">
        <div className={`h-14 w-14 rounded-2xl ${iconBg} flex items-center justify-center`}>
          <Icon className={`h-7 w-7 ${iconColor}`} strokeWidth={1.8} />
        </div>
        {onEdit && (
          <button onClick={onEdit} className="p-1.5 rounded-lg hover:bg-accent cursor-pointer transition-colors">
            <Pencil className="h-4 w-4 text-muted-foreground" />
          </button>
        )}
      </div>
      <div className="flex items-center gap-2 mb-1">
        <p className="text-sm text-muted-foreground">{label}</p>
        {live && (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold tracking-wider">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
            </span>
            LIVE
          </span>
        )}
      </div>
      <p className="text-3xl font-semibold tracking-tight tabular-nums">{value}</p>
      {sub && <div className="mt-2">{sub}</div>}
    </GlassCard>
  );
}

function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (value === display) return;
    const start = display;
    const target = value;
    const startTime = performance.now();
    const duration = 600;
    const tick = (now: number) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(start + (target - start) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return <>{format(display)}</>;
}

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [livePrices, setLivePrices] = useState<Record<string, { price: number; change: number; change_pct: number }>>({});
  const prevPricesRef = useRef<Record<string, number>>({});
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null);
  const [editBalance, setEditBalance] = useState("");
  const [savingBalance, setSavingBalance] = useState(false);
  const [macroRegime, setMacroRegime] = useState<MacroRegime | null>(null);
  const [showRegimeTilts, setShowRegimeTilts] = useState(false);
  const [blackSwan, setBlackSwan] = useState<BlackSwanResult | null>(null);
  const [blackSwanDismissed, setBlackSwanDismissed] = useState(false);

  useEffect(() => {
    Promise.all([
      api.overview(),
      api.portfolio().catch(() => null),
    ]).then(([ov, port]) => {
      setData(ov);
      if (port) setPortfolio(port);
    }).catch(() => {}).finally(() => setLoading(false));

    // Macro regime — fetch once on mount (cached 1h on server)
    api.macroRegime().then(setMacroRegime).catch(() => {});

    // Black swan check
    api.blackSwan().then(bs => {
      setBlackSwan(bs);
      // Check session storage for dismissal
      if (typeof window !== "undefined") {
        const dismissed = sessionStorage.getItem("blackSwanDismissed");
        if (dismissed === "true") setBlackSwanDismissed(true);
      }
    }).catch(() => {});
  }, []);

  // Live ticker polling — fetch fresh prices every 5 seconds
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await api.livePrices();
        if (cancelled) return;
        Object.entries(next).forEach(([sym, p]) => { prevPricesRef.current[sym] = p.price; });
        setLivePrices(next);
      } catch {}
    };
    poll();
    const i = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(i); };
  }, []);

  // Compute live totals from portfolio + live prices
  const liveTotals = useMemo(() => {
    if (!portfolio) return { value: 0, pnl: 0, pnlPct: 0 };
    let stockLiveValue = 0;
    for (const pos of portfolio.positions) {
      const live = livePrices[pos.symbol];
      const refPrice = pos.last_price || pos.avg_cost_price || 0;
      const fx = refPrice && pos.quantity ? (pos.market_value / (refPrice * pos.quantity)) : 1;
      const livePrice = live?.price ?? pos.last_price ?? pos.avg_cost_price ?? 0;
      stockLiveValue += livePrice * pos.quantity * fx;
    }
    // PnL is stock-performance only (cost basis is stocks only)
    const pnl = stockLiveValue - portfolio.total_cost;
    const pnlPct = portfolio.total_cost > 0 ? (pnl / portfolio.total_cost * 100) : 0;
    // Total portfolio value includes uninvested cash (already in CHF)
    const value = stockLiveValue + (portfolio.cash_balance ?? 0);
    return { value, pnl, pnlPct };
  }, [portfolio, livePrices]);

  const handleSetBalance = async () => {
    if (!editingAccountId || !editBalance) return;
    setSavingBalance(true);
    try {
      await api.setAccountBalance(editingAccountId, parseFloat(editBalance));
      // Reload data
      const [ov, port] = await Promise.all([api.overview(), api.portfolio()]);
      setData(ov);
      setPortfolio(port);
      setEditingAccountId(null);
      setEditBalance("");
    } catch {} finally {
      setSavingBalance(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-10 w-56" />
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-44" />)}
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  if (!data) return <p className="text-muted-foreground text-lg">Failed to load data.</p>;

  const pnlUp = data.portfolio_pnl >= 0;
  // Live-aware values: when portfolio data is loaded, use the live total instead of the cached overview value
  const livePortfolioValue = portfolio ? liveTotals.value : data.portfolio_value;
  const livePortfolioPnl = portfolio ? liveTotals.pnl : data.portfolio_pnl;
  const livePortfolioPnlPct = portfolio ? liveTotals.pnlPct : data.portfolio_pnl_pct;
  const liveNetWorth = data.net_worth - data.portfolio_value + livePortfolioValue;
  const liveUp = livePortfolioPnl >= 0;
  const bankAccounts = data.accounts.filter((a) => a.type === "bank");
  const ccAccounts = data.accounts.filter((a) => a.type === "credit_card");
  const bankTotal = bankAccounts.reduce((s, a) => s + a.balance, 0);
  const ccTotal = ccAccounts.reduce((s, a) => s + a.balance, 0);

  // Macro regime color mapping
  const regimeColors: Record<string, { pill: string; icon: React.ElementType }> = {
    "Expansionary": { pill: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400", icon: TrendingUp },
    "Late-Cycle": { pill: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400", icon: Minus },
    "Contractionary": { pill: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400", icon: TrendingDown },
    "Recovery": { pill: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400", icon: Activity },
    "Unknown": { pill: "bg-muted text-muted-foreground", icon: Minus },
  };
  const regime = macroRegime?.regime ?? "Unknown";
  const rc = regimeColors[regime] ?? regimeColors["Unknown"];
  const RegimeIcon = rc.icon;

  return (
    <div className="space-y-8">
      {/* Black Swan Banner */}
      <AnimatePresence>
        {blackSwan?.active && !blackSwanDismissed && (
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.3 }}
            className={`rounded-2xl px-5 py-4 flex items-start justify-between gap-4 ${blackSwan.severity === "critical" ? "bg-rose-100 dark:bg-rose-950/60 border border-rose-300 dark:border-rose-700" : blackSwan.severity === "warn" ? "bg-amber-100 dark:bg-amber-950/60 border border-amber-300 dark:border-amber-700" : "bg-blue-100 dark:bg-blue-950/60 border border-blue-300 dark:border-blue-700"}`}
          >
            <div className="flex items-start gap-3">
              <Activity className={`h-5 w-5 mt-0.5 shrink-0 ${blackSwan.severity === "critical" ? "text-rose-600" : blackSwan.severity === "warn" ? "text-amber-600" : "text-blue-600"}`} />
              <div>
                <p className={`text-[14px] font-semibold mb-1 ${blackSwan.severity === "critical" ? "text-rose-800 dark:text-rose-300" : blackSwan.severity === "warn" ? "text-amber-800 dark:text-amber-300" : "text-blue-800 dark:text-blue-300"}`}>
                  Black Swan Alert — {blackSwan.severity.charAt(0).toUpperCase() + blackSwan.severity.slice(1)}
                </p>
                <ul className="space-y-0.5">
                  {blackSwan.reasons.map((r, i) => (
                    <li key={i} className="text-[13px] text-foreground/70">{r.description}</li>
                  ))}
                </ul>
              </div>
            </div>
            <button
              onClick={() => { setBlackSwanDismissed(true); if (typeof window !== "undefined") sessionStorage.setItem("blackSwanDismissed", "true"); }}
              className="shrink-0 p-1 rounded-lg hover:bg-black/10 transition-colors cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
        <p className="text-sm font-medium text-primary mb-1">Overview</p>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-3xl font-bold tracking-tight">Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, {data.display_name}</h1>
          {macroRegime && (
            <div className="relative">
              <button
                onClick={() => setShowRegimeTilts(v => !v)}
                title={`VIX: ${macroRegime.indicators.vix ?? "N/A"} · Yield curve: ${macroRegime.indicators.yield_curve_bps ?? "N/A"}bps · Confidence: ${(macroRegime.confidence * 100).toFixed(0)}%`}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-semibold transition-all cursor-pointer hover:opacity-80 ${rc.pill}`}
              >
                <RegimeIcon className="h-3.5 w-3.5" />
                {regime}
              </button>
              <AnimatePresence>
                {showRegimeTilts && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.95 }}
                    transition={{ duration: 0.18 }}
                    className="absolute left-0 top-full mt-2 z-50 w-64 rounded-2xl bg-card border border-border shadow-lg p-4"
                  >
                    <p className="text-[13px] font-semibold mb-2">Suggested Sector Tilts</p>
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {macroRegime.sector_tilts.map(s => (
                        <span key={s} className="text-[11px] px-2.5 py-1 rounded-full bg-accent font-medium">{s}</span>
                      ))}
                    </div>
                    <div className="border-t border-border pt-2 space-y-1">
                      <p className="text-[11px] text-muted-foreground">VIX: <span className="text-foreground font-medium">{macroRegime.indicators.vix?.toFixed(1) ?? "N/A"}</span>{macroRegime.indicators.vix_zscore_60d !== null && <span> (z={macroRegime.indicators.vix_zscore_60d?.toFixed(2)})</span>}</p>
                      <p className="text-[11px] text-muted-foreground">Yield curve: <span className="text-foreground font-medium">{macroRegime.indicators.yield_curve_bps !== null ? `${macroRegime.indicators.yield_curve_bps}bps` : "N/A"}</span></p>
                      <p className="text-[11px] text-muted-foreground">10Y: <span className="text-foreground font-medium">{macroRegime.indicators.tnx_pct ?? "N/A"}%</span> · 3M: <span className="text-foreground font-medium">{macroRegime.indicators.irx_pct ?? "N/A"}%</span></p>
                      <p className="text-[11px] text-muted-foreground">Confidence: <span className="text-foreground font-medium">{(macroRegime.confidence * 100).toFixed(0)}%</span></p>
                    </div>
                    <button onClick={() => setShowRegimeTilts(false)} className="mt-2 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">Dismiss</button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </div>
        <p className="text-muted-foreground mt-1">Here's how your finances are looking today.</p>
      </motion.div>

      {/* Top Metric Cards */}
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        <MetricCard
          icon={Wallet} iconBg="bg-emerald-100 dark:bg-emerald-500/15" iconColor="text-emerald-600 dark:text-emerald-400"
          label="Total Balance" value={<AnimatedNumber value={liveNetWorth} format={formatCurrency} />} delay={0.05} live
        />
        <MetricCard
          icon={Landmark} iconBg="bg-blue-100 dark:bg-blue-500/15" iconColor="text-blue-600 dark:text-blue-400"
          label="Bank Account" value={formatCurrency(bankTotal)} delay={0.1}
          sub={bankAccounts.length > 0 ? <p className="text-sm text-muted-foreground">{bankAccounts[0].name}</p> : undefined}
          onEdit={bankAccounts.length > 0 ? () => { setEditingAccountId(bankAccounts[0].id); setEditBalance(String(Math.round(bankTotal))); } : undefined}
        />
        <MetricCard
          icon={TrendingUp} iconBg="bg-orange-100 dark:bg-orange-500/15" iconColor="text-orange-600 dark:text-orange-400"
          label="Portfolio" value={<AnimatedNumber value={livePortfolioValue} format={formatCurrency} />} delay={0.15} live
          sub={
            <p className={`text-sm font-medium flex items-center gap-1 ${liveUp ? "text-gain" : "text-loss"}`}>
              {liveUp ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {formatCurrency(Math.abs(livePortfolioPnl))} ({formatPct(livePortfolioPnlPct)})
            </p>
          }
        />
      </div>

      {/* Balance Edit Modal */}
      {editingAccountId && (
        <GlassCard delay={0}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[15px] font-semibold">Set Account Balance</h3>
            <button onClick={() => setEditingAccountId(null)} className="p-1.5 rounded-lg hover:bg-accent cursor-pointer">
              <span className="text-muted-foreground text-sm">Cancel</span>
            </button>
          </div>
          <p className="text-[13px] text-muted-foreground mb-3">
            Enter the actual current balance. An adjustment transaction will be created to match.
          </p>
          <div className="flex gap-3">
            <input
              type="number"
              value={editBalance}
              onChange={(e) => setEditBalance(e.target.value)}
              className="flex-1 h-11 rounded-xl bg-accent px-4 text-[15px] outline-none focus:ring-2 focus:ring-primary/40 tabular-nums"
              placeholder="e.g. 1234.56"
              autoFocus
            />
            <button
              onClick={handleSetBalance}
              disabled={savingBalance || !editBalance}
              className="h-11 px-6 rounded-xl bg-primary text-primary-foreground font-medium text-[14px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
            >
              {savingBalance ? "Saving..." : "Set Balance"}
            </button>
          </div>
        </GlassCard>
      )}

      {/* Credit Card row (if exists) */}
      {ccAccounts.length > 0 && (
        <GlassCard delay={0.2} className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl bg-rose-100 dark:bg-rose-500/15 flex items-center justify-center">
              <CreditCard className="h-6 w-6 text-rose-600 dark:text-rose-400" strokeWidth={1.8} />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Credit Card</p>
              <p className={`text-2xl font-semibold ${ccTotal < 0 ? "text-loss" : "text-gain"}`}>
                {formatCurrency(Math.abs(ccTotal))}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <p className="text-sm text-muted-foreground">{ccTotal < 0 ? "Outstanding balance" : "No balance"}</p>
            <button
              onClick={() => { setEditingAccountId(ccAccounts[0].id); setEditBalance(String(Math.round(Math.abs(ccTotal)))); }}
              className="p-1 rounded-lg hover:bg-accent cursor-pointer transition-colors"
            >
              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </div>
        </GlassCard>
      )}

      {/* Bottom: Recent Transactions + Budget Health */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Recent Transactions */}
        <GlassCard delay={0.25}>
          <h2 className="text-lg font-semibold mb-5">Recent Transactions</h2>
          {data.recent_transactions.length === 0 ? (
            <div className="text-center py-12">
              <Banknote className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" strokeWidth={1.2} />
              <p className="text-muted-foreground">No transactions yet</p>
              <p className="text-sm text-muted-foreground/60 mt-1">Import a bank statement to get started</p>
            </div>
          ) : (
            <div className="space-y-4">
              {data.recent_transactions.map((t, i) => (
                <motion.div
                  key={t.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.05, duration: 0.3 }}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className={`h-11 w-11 rounded-2xl flex items-center justify-center text-[15px] font-semibold ${
                      t.amount < 0
                        ? "bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400"
                        : "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400"
                    }`}>
                      {t.merchant.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-[15px] font-medium">{t.merchant}</p>
                      <p className="text-[13px] text-muted-foreground">
                        {t.date}{t.category_name && ` \u00B7 ${t.category_name}`}
                      </p>
                    </div>
                  </div>
                  <p className={`text-[15px] font-semibold tabular-nums ${t.amount < 0 ? "text-loss" : "text-gain"}`}>
                    {formatCurrency(t.amount, t.currency)}
                  </p>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        {/* Budget Health */}
        <GlassCard delay={0.3}>
          <h2 className="text-lg font-semibold mb-5">Budget Health</h2>
          {data.budget_health.length === 0 ? (
            <div className="text-center py-12">
              <TrendingUp className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" strokeWidth={1.2} />
              <p className="text-muted-foreground">No budgets set</p>
              <p className="text-sm text-muted-foreground/60 mt-1">Create a budget in Settings</p>
            </div>
          ) : (
            <div className="space-y-5">
              {data.budget_health.map((b, i) => {
                const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
                const over = pct > 100;
                return (
                  <motion.div
                    key={b.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.35 + i * 0.05 }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[15px] font-medium">{b.name}</span>
                      <span className="text-[13px] text-muted-foreground tabular-nums">
                        {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                      </span>
                    </div>
                    <div className="h-3 rounded-full bg-secondary overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(pct, 100)}%` }}
                        transition={{ duration: 0.8, delay: 0.4 + i * 0.05, ease: [0.25, 0.46, 0.45, 0.94] }}
                        className={`h-full rounded-full ${over ? "bg-loss" : "bg-primary"}`}
                      />
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
