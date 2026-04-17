"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { motion } from "motion/react";
import { api, Overview, PortfolioSummary } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { LivePill } from "@/components/live-pill";
import { CategoryPill } from "@/components/category-pill";
import {
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Landmark,
  CreditCard,
  TrendingUp,
  Banknote,
  Pencil,
} from "lucide-react";

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-muted ${className ?? ""}`} />;
}

function MetricCard({
  icon: Icon,
  iconBg,
  iconColor,
  glowColor,
  label,
  value,
  sub,
  delay,
  live,
  onEdit,
}: {
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  glowColor: string;
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  delay: number;
  live?: boolean;
  onEdit?: () => void;
}) {
  return (
    <GlassCard delay={delay} className="relative overflow-hidden">
      {/* Ambient glow blob */}
      <div
        className="pointer-events-none absolute -top-10 -right-10 h-[140px] w-[140px] rounded-full opacity-35 blur-[40px]"
        style={{ background: glowColor }}
      />
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-5">
          <div className={`h-[44px] w-[44px] rounded-[14px] ${iconBg} flex items-center justify-center`}>
            <Icon className={`h-6 w-6 ${iconColor}`} strokeWidth={1.8} />
          </div>
          <div className="flex items-center gap-2">
            {live && <LivePill />}
            {onEdit && (
              <button
                onClick={onEdit}
                className="p-1.5 rounded-lg hover:bg-accent cursor-pointer transition-colors"
              >
                <Pencil className="h-4 w-4 text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
        <p className="text-[12px] font-medium text-muted-foreground mb-1">{label}</p>
        <p className="font-mono tabular-nums text-[28px] font-bold" style={{letterSpacing: '-0.8px'}}>{value}</p>
        {sub && <div className="mt-2">{sub}</div>}
      </div>
    </GlassCard>
  );
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

  useEffect(() => {
    Promise.all([
      api.overview(),
      api.portfolio().catch(() => null),
    ]).then(([ov, port]) => {
      setData(ov);
      if (port) setPortfolio(port);
    }).catch(() => {}).finally(() => setLoading(false));
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
        <div className="grid gap-[18px] grid-cols-3">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-44" />)}
        </div>
        <div className="grid gap-[18px] grid-cols-[1.3fr_1fr]">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  if (!data) return <p className="text-muted-foreground text-[14px]">Failed to load data.</p>;

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
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";

  return (
    <div className="space-y-8">
      {/* Greeting */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h2 className="text-[28px] font-bold" style={{letterSpacing: '-0.6px'}}>
          Good {greeting}, {data.display_name}
        </h2>
        <p className="text-muted-foreground mt-1 text-[14px]">
          Here&apos;s how your finances are looking today.
        </p>
      </motion.div>

      {/* Top Metric Cards */}
      <div className="grid gap-[18px] grid-cols-3">
        <MetricCard
          icon={Wallet}
          iconBg="bg-emerald-100 dark:bg-emerald-500/15"
          iconColor="text-emerald-600 dark:text-emerald-400"
          glowColor="linear-gradient(135deg, #16a34a, #22c55e)"
          label="Total Balance"
          value={<AnimatedNumber value={liveNetWorth} format={formatCurrency} />}
          delay={0.05}
          live
        />
        <MetricCard
          icon={Landmark}
          iconBg="bg-blue-100 dark:bg-blue-500/15"
          iconColor="text-blue-600 dark:text-blue-400"
          glowColor="linear-gradient(135deg, #2f5bff, #8b5cf6)"
          label="Bank Accounts"
          value={formatCurrency(bankTotal)}
          delay={0.1}
          sub={
            bankAccounts.length > 0 ? (
              <p className="text-[13px] text-muted-foreground">{bankAccounts[0].name}</p>
            ) : undefined
          }
          onEdit={
            bankAccounts.length > 0
              ? () => {
                  setEditingAccountId(bankAccounts[0].id);
                  setEditBalance(String(Math.round(bankTotal)));
                }
              : undefined
          }
        />
        <MetricCard
          icon={TrendingUp}
          iconBg="bg-orange-100 dark:bg-orange-500/15"
          iconColor="text-orange-600 dark:text-orange-400"
          glowColor="linear-gradient(135deg, #f59e0b, #ef4444)"
          label="Portfolio"
          value={<AnimatedNumber value={livePortfolioValue} format={formatCurrency} />}
          delay={0.15}
          live
          sub={
            <p className={`text-[13px] font-semibold flex items-center gap-1 ${liveUp ? "text-gain" : "text-loss"}`}>
              {liveUp ? (
                <ArrowUpRight className="h-4 w-4" />
              ) : (
                <ArrowDownRight className="h-4 w-4" />
              )}
              {formatCurrency(Math.abs(livePortfolioPnl))} ({formatPct(livePortfolioPnlPct)})
            </p>
          }
        />
      </div>

      {/* Inline Balance Edit */}
      {editingAccountId && (
        <GlassCard delay={0}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-[15px] font-semibold">Set Account Balance</h3>
            <button
              onClick={() => setEditingAccountId(null)}
              className="p-1.5 rounded-lg hover:bg-accent cursor-pointer"
            >
              <span className="text-muted-foreground text-[13px]">Cancel</span>
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
            <div className="h-12 w-12 rounded-2xl bg-rose-100 dark:bg-rose-500/15 flex items-center justify-center flex-shrink-0">
              <CreditCard className="h-6 w-6 text-rose-600 dark:text-rose-400" strokeWidth={1.8} />
            </div>
            <div>
              <p className="text-[12px] text-muted-foreground">Credit Card</p>
              <p className={`font-mono tabular-nums text-[28px] font-bold ${ccTotal < 0 ? "text-loss" : "text-gain"}`} style={{letterSpacing: '-0.8px'}}>
                {formatCurrency(Math.abs(ccTotal))}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <p className="text-[13px] text-muted-foreground">
              {ccTotal < 0 ? "Outstanding balance" : "No balance"}
            </p>
            <button
              onClick={() => {
                setEditingAccountId(ccAccounts[0].id);
                setEditBalance(String(Math.round(Math.abs(ccTotal))));
              }}
              className="p-1 rounded-lg hover:bg-accent cursor-pointer transition-colors"
            >
              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </div>
        </GlassCard>
      )}

      {/* Bottom: Recent Transactions + Budget Health */}
      <div className="grid gap-[18px] grid-cols-[1.3fr_1fr]">
        {/* Recent Transactions */}
        <GlassCard delay={0.25}>
          <h2 className="text-[16px] font-semibold mb-5">Recent Transactions</h2>
          {data.recent_transactions.length === 0 ? (
            <div className="text-center py-12">
              <Banknote
                className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3"
                strokeWidth={1.2}
              />
              <p className="text-muted-foreground">No transactions yet</p>
              <p className="text-[12px] text-muted-foreground/60 mt-1">
                Import a bank statement to get started
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {data.recent_transactions.map((t, i) => (
                <motion.div
                  key={t.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.05, duration: 0.3 }}
                  className="flex items-center justify-between py-1"
                >
                  <div className="flex items-center gap-3">
                    {/* Merchant avatar circle */}
                    <div
                      className={`h-10 w-10 rounded-[13px] flex items-center justify-center text-[14px] font-bold flex-shrink-0 ${
                        t.amount < 0
                          ? "bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400"
                          : "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400"
                      }`}
                    >
                      {t.merchant.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-[14px] font-medium leading-snug font-sans">{t.merchant}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-[12px] text-muted-foreground">{t.date}</span>
                        {t.category_name && (
                          <CategoryPill name={t.category_name} />
                        )}
                      </div>
                    </div>
                  </div>
                  <p
                    className={`font-mono tabular-nums text-[14px] font-semibold ${
                      t.amount < 0 ? "text-loss" : "text-gain"
                    }`}
                  >
                    {formatCurrency(t.amount, t.currency)}
                  </p>
                </motion.div>
              ))}
            </div>
          )}
        </GlassCard>

        {/* Budget Health */}
        <GlassCard delay={0.3}>
          <h2 className="text-[16px] font-semibold mb-5">Budget Health</h2>
          {data.budget_health.length === 0 ? (
            <div className="text-center py-12">
              <TrendingUp
                className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3"
                strokeWidth={1.2}
              />
              <p className="text-muted-foreground">No budgets set</p>
              <p className="text-[12px] text-muted-foreground/60 mt-1">Create a budget in Settings</p>
            </div>
          ) : (
            <div className="space-y-5">
              {data.budget_health.slice(0, 5).map((b, i) => {
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
                      <span className="text-[12px] font-medium">{b.name}</span>
                      <span className="font-mono tabular-nums text-[12px] text-muted-foreground">
                        {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-secondary overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(pct, 100)}%` }}
                        transition={{
                          duration: 0.8,
                          delay: 0.4 + i * 0.05,
                          ease: [0.25, 0.46, 0.45, 0.94],
                        }}
                        className="h-full rounded-full"
                        style={{
                          background: over
                            ? "linear-gradient(90deg, #ef4444, #f97316)"
                            : "linear-gradient(90deg, #2f5bff, #8b5cf6)",
                        }}
                      />
                    </div>
                    {over && (
                      <p className="text-[11px] text-red-500 mt-1 font-medium">
                        Over budget by {formatCurrency(b.spent - b.amount)}
                      </p>
                    )}
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
