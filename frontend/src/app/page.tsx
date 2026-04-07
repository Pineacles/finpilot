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
        <Skeleton className="h-10 w-48" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32" />)}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  if (!data) return <p className="text-muted-foreground text-base">Failed to load data.</p>;

  const pnlUp = data.portfolio_pnl >= 0;
  const bankAccounts = data.accounts.filter((a) => a.type === "bank");
  const ccAccounts = data.accounts.filter((a) => a.type === "credit_card");
  const bankTotal = bankAccounts.reduce((s, a) => s + a.balance, 0);
  const ccTotal = ccAccounts.reduce((s, a) => s + a.balance, 0);

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold">Overview</h1>

      {/* Net Worth - hero */}
      <Card>
        <CardContent className="py-8 px-8">
          <div className="flex items-center gap-2 mb-2">
            <Wallet className="h-5 w-5 text-muted-foreground" />
            <span className="text-sm font-medium text-muted-foreground">Net Worth</span>
          </div>
          <p className="text-5xl font-bold tracking-tight">{formatCurrency(data.net_worth)}</p>
        </CardContent>
      </Card>

      {/* Account Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="py-6 px-6">
            <div className="flex items-center gap-2 mb-3">
              <Landmark className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium text-muted-foreground">Bank</span>
            </div>
            <p className="text-2xl font-bold text-gain">{formatCurrency(bankTotal)}</p>
            {bankAccounts.map((a) => (
              <p key={a.id} className="text-sm text-muted-foreground mt-1">{a.name}</p>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="py-6 px-6">
            <div className="flex items-center gap-2 mb-3">
              <CreditCard className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium text-muted-foreground">Credit Card</span>
            </div>
            {ccAccounts.length === 0 ? (
              <p className="text-2xl font-bold text-muted-foreground">--</p>
            ) : (
              <>
                <p className={`text-2xl font-bold ${ccTotal < 0 ? "text-loss" : "text-gain"}`}>
                  {formatCurrency(Math.abs(ccTotal))}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  {ccTotal < 0 ? "Outstanding" : "Paid"}
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="py-6 px-6">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp className="h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium text-muted-foreground">Portfolio</span>
            </div>
            <p className="text-2xl font-bold">{formatCurrency(data.portfolio_value)}</p>
            <p className={`text-sm mt-1 flex items-center gap-1 font-medium ${pnlUp ? "text-gain" : "text-loss"}`}>
              {pnlUp ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
              {formatCurrency(Math.abs(data.portfolio_pnl))} ({formatPct(data.portfolio_pnl_pct)})
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="py-6 px-6">
            <span className="text-sm font-medium text-muted-foreground">Accounts</span>
            <p className="text-2xl font-bold mt-3">{data.accounts.length}</p>
            <div className="flex flex-wrap gap-2 mt-3">
              {data.accounts.map((a) => (
                <span key={a.id} className="text-xs px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground">{a.name}</span>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Two columns */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Recent Transactions</CardTitle>
          </CardHeader>
          <CardContent>
            {data.recent_transactions.length === 0 ? (
              <p className="text-base text-muted-foreground">No transactions yet.</p>
            ) : (
              <div className="space-y-4">
                {data.recent_transactions.map((t) => (
                  <div key={t.id} className="flex items-center justify-between py-1">
                    <div>
                      <p className="text-base font-medium">{t.merchant}</p>
                      <p className="text-sm text-muted-foreground">
                        {t.date}{t.category_name && ` \u00B7 ${t.category_name}`}
                      </p>
                    </div>
                    <p className={`text-base font-semibold tabular-nums ${t.amount < 0 ? "text-loss" : "text-gain"}`}>
                      {formatCurrency(t.amount, t.currency)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Budget Health</CardTitle>
          </CardHeader>
          <CardContent>
            {data.budget_health.length === 0 ? (
              <p className="text-base text-muted-foreground">No budgets set.</p>
            ) : (
              <div className="space-y-5">
                {data.budget_health.map((b) => {
                  const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
                  const over = pct > 100;
                  return (
                    <div key={b.id}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-base font-medium">{b.name}</span>
                        <span className="text-sm text-muted-foreground tabular-nums">
                          {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-secondary overflow-hidden">
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
