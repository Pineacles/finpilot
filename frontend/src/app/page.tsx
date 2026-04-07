"use client";

import { useEffect, useState } from "react";
import { api, Overview } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Landmark,
  CreditCard,
  TrendingUp,
  MoreHorizontal,
} from "lucide-react";

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
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}
        </div>
        <Skeleton className="h-72 rounded-2xl" />
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
      <h1 className="text-2xl font-bold">Finance Dashboard</h1>

      {/* Top Metric Cards — colorful icons like the reference */}
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {/* Total Balance */}
        <Card className="rounded-2xl shadow-sm">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="h-12 w-12 rounded-2xl bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <Wallet className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
              <button className="text-muted-foreground hover:text-foreground cursor-pointer">
                <MoreHorizontal className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-1">Total Balance</p>
            <p className="text-3xl font-bold tracking-tight">{formatCurrency(data.net_worth)}</p>
          </CardContent>
        </Card>

        {/* Bank Balance */}
        <Card className="rounded-2xl shadow-sm">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="h-12 w-12 rounded-2xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                <Landmark className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
              <button className="text-muted-foreground hover:text-foreground cursor-pointer">
                <MoreHorizontal className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-1">Bank Account</p>
            <p className="text-3xl font-bold tracking-tight">{formatCurrency(bankTotal)}</p>
          </CardContent>
        </Card>

        {/* Credit Card / Portfolio */}
        <Card className="rounded-2xl shadow-sm">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="h-12 w-12 rounded-2xl bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
                <TrendingUp className="h-6 w-6 text-orange-600 dark:text-orange-400" />
              </div>
              <button className="text-muted-foreground hover:text-foreground cursor-pointer">
                <MoreHorizontal className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-1">Portfolio</p>
            <p className="text-3xl font-bold tracking-tight">{formatCurrency(data.portfolio_value)}</p>
            <p className={`text-sm mt-1 flex items-center gap-1 font-medium ${pnlUp ? "text-gain" : "text-loss"}`}>
              {pnlUp ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {formatCurrency(Math.abs(data.portfolio_pnl))} ({formatPct(data.portfolio_pnl_pct)})
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Credit Card + Accounts row */}
      {(ccAccounts.length > 0 || data.accounts.length > 2) && (
        <div className="grid gap-5 md:grid-cols-2">
          {ccAccounts.length > 0 && (
            <Card className="rounded-2xl shadow-sm">
              <CardContent className="p-6">
                <div className="flex items-center gap-3 mb-3">
                  <div className="h-10 w-10 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <CreditCard className="h-5 w-5 text-red-600 dark:text-red-400" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Credit Card</p>
                    <p className={`text-2xl font-bold ${ccTotal < 0 ? "text-loss" : "text-gain"}`}>
                      {formatCurrency(Math.abs(ccTotal))}
                    </p>
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">{ccTotal < 0 ? "Outstanding balance" : "No balance"}</p>
              </CardContent>
            </Card>
          )}
          <Card className="rounded-2xl shadow-sm">
            <CardContent className="p-6">
              <p className="text-sm text-muted-foreground mb-3">All Accounts</p>
              <div className="space-y-3">
                {data.accounts.map((a) => (
                  <div key={a.id} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${
                        a.type === "bank" ? "bg-blue-100 dark:bg-blue-900/30" :
                        a.type === "credit_card" ? "bg-red-100 dark:bg-red-900/30" :
                        "bg-purple-100 dark:bg-purple-900/30"
                      }`}>
                        {a.type === "bank" ? <Landmark className="h-4 w-4 text-blue-600 dark:text-blue-400" /> :
                         a.type === "credit_card" ? <CreditCard className="h-4 w-4 text-red-600 dark:text-red-400" /> :
                         <TrendingUp className="h-4 w-4 text-purple-600 dark:text-purple-400" />}
                      </div>
                      <span className="text-sm font-medium">{a.name}</span>
                    </div>
                    <span className="text-sm font-semibold tabular-nums">{formatCurrency(a.balance)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Recent Transactions + Budget Health */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="rounded-2xl shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg font-semibold">Recent Transactions</CardTitle>
          </CardHeader>
          <CardContent>
            {data.recent_transactions.length === 0 ? (
              <p className="text-muted-foreground">No transactions yet.</p>
            ) : (
              <div className="space-y-4">
                {data.recent_transactions.map((t) => (
                  <div key={t.id} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`h-10 w-10 rounded-xl flex items-center justify-center text-sm font-bold ${
                        t.amount < 0 ? "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400" : "bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400"
                      }`}>
                        {t.merchant.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-[15px] font-medium">{t.merchant}</p>
                        <p className="text-sm text-muted-foreground">{t.date}{t.category_name && ` \u00B7 ${t.category_name}`}</p>
                      </div>
                    </div>
                    <p className={`text-[15px] font-semibold tabular-nums ${t.amount < 0 ? "text-loss" : "text-gain"}`}>
                      {formatCurrency(t.amount, t.currency)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-2xl shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg font-semibold">Budget Health</CardTitle>
          </CardHeader>
          <CardContent>
            {data.budget_health.length === 0 ? (
              <p className="text-muted-foreground">No budgets set.</p>
            ) : (
              <div className="space-y-5">
                {data.budget_health.map((b) => {
                  const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
                  const over = pct > 100;
                  return (
                    <div key={b.id}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[15px] font-medium">{b.name}</span>
                        <span className="text-sm text-muted-foreground tabular-nums">
                          {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                        </span>
                      </div>
                      <div className="h-2.5 rounded-full bg-secondary overflow-hidden">
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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
