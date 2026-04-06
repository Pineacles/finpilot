"use client";

import { useEffect, useState } from "react";
import { api, Overview } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Wallet,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  CreditCard,
} from "lucide-react";

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.overview().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Overview</h1>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i}><CardContent className="p-6"><Skeleton className="h-20" /></CardContent></Card>
          ))}
        </div>
      </div>
    );
  }

  if (!data) return <p>Failed to load data</p>;

  const pnlPositive = data.portfolio_pnl >= 0;

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Overview</h1>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Net Worth</CardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(data.net_worth)}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Portfolio Value</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(data.portfolio_value)}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Portfolio P&L</CardTitle>
            {pnlPositive ? <ArrowUpRight className="h-4 w-4 text-green-500" /> : <ArrowDownRight className="h-4 w-4 text-red-500" />}
          </CardHeader>
          <CardContent>
            <p className={`text-2xl font-bold ${pnlPositive ? "text-green-500" : "text-red-500"}`}>
              {formatCurrency(data.portfolio_pnl)}
            </p>
            <p className={`text-xs ${pnlPositive ? "text-green-500" : "text-red-500"}`}>
              {formatPct(data.portfolio_pnl_pct)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Accounts</CardTitle>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{data.accounts.length}</p>
            <div className="flex gap-1 mt-1">
              {data.accounts.map((a) => (
                <Badge key={a.id} variant="secondary" className="text-xs">{a.name}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Recent Transactions</CardTitle></CardHeader>
          <CardContent>
            {data.recent_transactions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No transactions yet. Sync Viseca to import.</p>
            ) : (
              <div className="space-y-3">
                {data.recent_transactions.map((t) => (
                  <div key={t.id} className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{t.merchant}</p>
                      <p className="text-xs text-muted-foreground">{t.date} {t.category_name && `· ${t.category_name}`}</p>
                    </div>
                    <p className={`text-sm font-medium ${t.amount < 0 ? "text-red-500" : "text-green-500"}`}>
                      {formatCurrency(t.amount, t.currency)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Budget Health</CardTitle></CardHeader>
          <CardContent>
            {data.budget_health.length === 0 ? (
              <p className="text-sm text-muted-foreground">No budgets set. Go to Budgets to create one.</p>
            ) : (
              <div className="space-y-4">
                {data.budget_health.map((b) => {
                  const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
                  const over = pct > 100;
                  return (
                    <div key={b.id}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{b.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-secondary">
                        <div
                          className={`h-full rounded-full ${over ? "bg-red-500" : "bg-primary"}`}
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
