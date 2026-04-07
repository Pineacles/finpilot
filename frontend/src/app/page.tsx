"use client";

import { useEffect, useState } from "react";
import { api, Overview } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.overview().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-10">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!data) return <p className="text-muted-foreground">Failed to load data.</p>;

  const pnlUp = data.portfolio_pnl >= 0;
  const bankAccounts = data.accounts.filter((a) => a.type === "bank");
  const ccAccounts = data.accounts.filter((a) => a.type === "credit_card");
  const bankTotal = bankAccounts.reduce((s, a) => s + a.balance, 0);
  const ccTotal = ccAccounts.reduce((s, a) => s + a.balance, 0);

  return (
    <div className="space-y-10">
      {/* Page header — left-aligned, no icon clutter */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-muted-foreground mt-1">Your financial snapshot</p>
      </div>

      {/* Net worth hero — large, prominent, no card wrapper */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">Net Worth</p>
        <p className="text-4xl font-bold tracking-tight">{formatCurrency(data.net_worth)}</p>
      </div>

      {/* Account balances — clean grid, no heavy cards */}
      <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">Bank</p>
          <p className="text-2xl font-semibold text-gain">{formatCurrency(bankTotal)}</p>
          {bankAccounts.map((a) => (
            <p key={a.id} className="text-xs text-muted-foreground mt-1">{a.name}</p>
          ))}
        </div>

        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">Credit Card</p>
          {ccAccounts.length === 0 ? (
            <p className="text-2xl font-semibold text-muted-foreground">--</p>
          ) : (
            <>
              <p className={`text-2xl font-semibold ${ccTotal < 0 ? "text-loss" : "text-gain"}`}>
                {formatCurrency(Math.abs(ccTotal))}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {ccTotal < 0 ? "Outstanding" : "Paid"}
              </p>
            </>
          )}
        </div>

        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">Portfolio</p>
          <p className="text-2xl font-semibold">{formatCurrency(data.portfolio_value)}</p>
          <p className={`text-xs mt-1 flex items-center gap-1 ${pnlUp ? "text-gain" : "text-loss"}`}>
            {pnlUp ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {formatCurrency(Math.abs(data.portfolio_pnl))} ({formatPct(data.portfolio_pnl_pct)})
          </p>
        </div>

        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">Accounts</p>
          <p className="text-2xl font-semibold">{data.accounts.length}</p>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {data.accounts.map((a) => (
              <span key={a.id} className="text-[11px] px-2 py-0.5 rounded-md bg-muted text-muted-foreground">{a.name}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Divider — subtle breathing room */}
      <div className="border-t border-border" />

      {/* Two columns: Recent transactions + Budget health */}
      <div className="grid gap-10 lg:grid-cols-2">
        {/* Recent Transactions */}
        <div>
          <h2 className="text-sm font-semibold mb-4">Recent Transactions</h2>
          {data.recent_transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No transactions yet.</p>
          ) : (
            <div className="space-y-3">
              {data.recent_transactions.map((t) => (
                <div key={t.id} className="flex items-center justify-between py-1">
                  <div>
                    <p className="text-sm font-medium">{t.merchant}</p>
                    <p className="text-xs text-muted-foreground">
                      {t.date}{t.category_name && ` \u00B7 ${t.category_name}`}
                    </p>
                  </div>
                  <p className={`text-sm font-semibold tabular-nums ${t.amount < 0 ? "text-loss" : "text-gain"}`}>
                    {formatCurrency(t.amount, t.currency)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Budget Health */}
        <div>
          <h2 className="text-sm font-semibold mb-4">Budget Health</h2>
          {data.budget_health.length === 0 ? (
            <p className="text-sm text-muted-foreground">No budgets set.</p>
          ) : (
            <div className="space-y-4">
              {data.budget_health.map((b) => {
                const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
                const over = pct > 100;
                return (
                  <div key={b.id}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-medium">{b.name}</span>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${over ? "bg-loss" : "bg-primary"}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
