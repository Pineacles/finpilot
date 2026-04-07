"use client";

import { useEffect, useState } from "react";
import { api, Overview } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Wallet,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  CreditCard,
  Landmark,
  CircleDollarSign,
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
  const bankAccounts = data.accounts.filter((a) => a.type === "bank");
  const ccAccounts = data.accounts.filter((a) => a.type === "credit_card");
  const bankTotal = bankAccounts.reduce((s, a) => s + a.balance, 0);
  const ccTotal = ccAccounts.reduce((s, a) => s + a.balance, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Overview</h1>

      {/* Top KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Net Worth</CardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(data.net_worth)}</p>
            <p className="text-xs text-muted-foreground mt-1">Bank + Portfolio + Credit Card</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Bank Balance</CardTitle>
            <Landmark className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-green-500">{formatCurrency(bankTotal)}</p>
            {bankAccounts.map((a) => (
              <p key={a.id} className="text-xs text-muted-foreground">{a.name}</p>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Credit Card</CardTitle>
            <CreditCard className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {ccAccounts.length === 0 ? (
              <>
                <p className="text-2xl font-bold text-muted-foreground">-</p>
                <p className="text-xs text-muted-foreground">No credit card imported</p>
              </>
            ) : (
              <>
                <p className={`text-2xl font-bold ${ccTotal < 0 ? "text-red-500" : "text-green-500"}`}>
                  {formatCurrency(Math.abs(ccTotal))}
                </p>
                <p className="text-xs text-muted-foreground">
                  {ccTotal < 0 ? "Outstanding balance" : "No balance"}
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Portfolio</CardTitle>
            {pnlPositive ? <ArrowUpRight className="h-4 w-4 text-green-500" /> : <ArrowDownRight className="h-4 w-4 text-red-500" />}
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(data.portfolio_value)}</p>
            <p className={`text-xs ${pnlPositive ? "text-green-500" : "text-red-500"}`}>
              {formatCurrency(data.portfolio_pnl)} ({formatPct(data.portfolio_pnl_pct)})
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Transactions */}
        <Card>
          <CardHeader><CardTitle>Recent Transactions</CardTitle></CardHeader>
          <CardContent>
            {data.recent_transactions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No transactions yet.</p>
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

        {/* Budget Health */}
        <Card>
          <CardHeader><CardTitle>Budget Health</CardTitle></CardHeader>
          <CardContent>
            {data.budget_health.length === 0 ? (
              <p className="text-sm text-muted-foreground">No budgets set.</p>
            ) : (
              <div className="space-y-4">
                {data.budget_health.map((b) => {
                  const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
                  return (
                    <div key={b.id}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{b.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                        </span>
                      </div>
                      <Progress value={Math.min(pct, 100)} className={pct > 100 ? "[&>div]:bg-red-500" : ""} />
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
