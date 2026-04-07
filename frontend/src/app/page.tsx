"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, Overview } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import {
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Landmark,
  CreditCard,
  TrendingUp,
  Banknote,
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

function MetricCard({ icon: Icon, iconBg, iconColor, label, value, sub, delay }: {
  icon: React.ElementType; iconBg: string; iconColor: string;
  label: string; value: string; sub?: React.ReactNode; delay: number;
}) {
  return (
    <GlassCard delay={delay}>
      <div className="flex items-start justify-between mb-5">
        <div className={`h-14 w-14 rounded-2xl ${iconBg} flex items-center justify-center`}>
          <Icon className={`h-7 w-7 ${iconColor}`} strokeWidth={1.8} />
        </div>
      </div>
      <p className="text-sm text-muted-foreground mb-1">{label}</p>
      <p className="text-3xl font-semibold tracking-tight">{value}</p>
      {sub && <div className="mt-2">{sub}</div>}
    </GlassCard>
  );
}

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.overview().then(setData).finally(() => setLoading(false));
  }, []);

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
  const bankAccounts = data.accounts.filter((a) => a.type === "bank");
  const ccAccounts = data.accounts.filter((a) => a.type === "credit_card");
  const bankTotal = bankAccounts.reduce((s, a) => s + a.balance, 0);
  const ccTotal = ccAccounts.reduce((s, a) => s + a.balance, 0);

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
        <p className="text-sm font-medium text-primary mb-1">Overview</p>
        <h1 className="text-3xl font-bold tracking-tight">Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, Admin</h1>
        <p className="text-muted-foreground mt-1">Here's how your finances are looking today.</p>
      </motion.div>

      {/* Top Metric Cards */}
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        <MetricCard
          icon={Wallet} iconBg="bg-emerald-100 dark:bg-emerald-500/15" iconColor="text-emerald-600 dark:text-emerald-400"
          label="Total Balance" value={formatCurrency(data.net_worth)} delay={0.05}
        />
        <MetricCard
          icon={Landmark} iconBg="bg-blue-100 dark:bg-blue-500/15" iconColor="text-blue-600 dark:text-blue-400"
          label="Bank Account" value={formatCurrency(bankTotal)} delay={0.1}
          sub={bankAccounts.length > 0 ? <p className="text-sm text-muted-foreground">{bankAccounts[0].name}</p> : undefined}
        />
        <MetricCard
          icon={TrendingUp} iconBg="bg-orange-100 dark:bg-orange-500/15" iconColor="text-orange-600 dark:text-orange-400"
          label="Portfolio" value={formatCurrency(data.portfolio_value)} delay={0.15}
          sub={
            <p className={`text-sm font-medium flex items-center gap-1 ${pnlUp ? "text-gain" : "text-loss"}`}>
              {pnlUp ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {formatCurrency(Math.abs(data.portfolio_pnl))} ({formatPct(data.portfolio_pnl_pct)})
            </p>
          }
        />
      </div>

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
          <p className="text-sm text-muted-foreground">{ccTotal < 0 ? "Outstanding balance" : "No balance"}</p>
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
