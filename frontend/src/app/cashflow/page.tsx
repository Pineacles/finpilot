"use client";

import { useEffect, useState } from "react";
import { api, CashFlowMonth, RecurringExpense } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { CalendarClock } from "lucide-react";

export default function CashFlowPage() {
  const [cashflow, setCashflow] = useState<CashFlowMonth[]>([]);
  const [recurring, setRecurring] = useState<RecurringExpense[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.cashflow(12), api.recurring()])
      .then(([cf, r]) => { setCashflow(cf); setRecurring(r); })
      .finally(() => setLoading(false));
  }, []);

  const totalRecurring = recurring.filter((r) => r.active).reduce((sum, r) => sum + r.amount, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Cash Flow</h1>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Monthly Recurring</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-bold text-red-500">{formatCurrency(totalRecurring)}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Avg Monthly Net</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {cashflow.length > 0
                ? formatCurrency(cashflow.reduce((s, c) => s + c.net, 0) / cashflow.length)
                : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Active Subscriptions</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-bold">{recurring.filter((r) => r.active).length}</p></CardContent>
        </Card>
      </div>

      {/* Chart */}
      <Card>
        <CardHeader><CardTitle>Income vs Expenses (12 months)</CardTitle></CardHeader>
        <CardContent className="h-80">
          {cashflow.length === 0 ? (
            <p className="text-sm text-muted-foreground">No data yet. Import transactions to see cash flow.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cashflow}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                <Legend />
                <Bar dataKey="income" fill="#10b981" name="Income" />
                <Bar dataKey="expenses" fill="#ef4444" name="Expenses" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Recurring Expenses */}
      <Card>
        <CardHeader><CardTitle>Recurring Expenses</CardTitle></CardHeader>
        <CardContent>
          {recurring.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recurring expenses tracked yet.</p>
          ) : (
            <div className="space-y-3">
              {recurring.map((r) => (
                <div key={r.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <CalendarClock className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-sm font-medium">{r.name}</p>
                      <p className="text-xs text-muted-foreground capitalize">{r.frequency} · Next: {r.next_due_date}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-red-500">{formatCurrency(r.amount, r.currency)}</span>
                    {!r.active && <Badge variant="secondary">Paused</Badge>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
