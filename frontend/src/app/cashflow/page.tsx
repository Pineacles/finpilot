"use client";

import { useEffect, useState } from "react";
import { api, CashFlowMonth, RecurringExpense } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { GlassCard } from "@/components/glass-card";
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
import { CalendarClock, TrendingUp, RefreshCw } from "lucide-react";

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
  const avgNet = cashflow.length > 0 ? cashflow.reduce((s, c) => s + c.net, 0) / cashflow.length : 0;
  const activeSubs = recurring.filter((r) => r.active).length;

  const kpis = [
    {
      label: "Monthly Recurring",
      value: formatCurrency(totalRecurring),
      color: "text-loss",
      accent: "linear-gradient(135deg, #ef4444, #f97316)",
      Icon: RefreshCw,
    },
    {
      label: "Avg Monthly Net",
      value: cashflow.length > 0 ? formatCurrency(avgNet) : "—",
      color: "text-gain",
      accent: "linear-gradient(135deg, #16a34a, #22c55e)",
      Icon: TrendingUp,
    },
    {
      label: "Active Subscriptions",
      value: String(activeSubs),
      color: "",
      accent: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
      Icon: CalendarClock,
    },
  ];

  return (
    <div className="space-y-6 p-1">
      {/* Header */}
      <GlassCard delay={0}>
        <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-1">Cash Flow</p>
        <h1 className="text-2xl font-bold tracking-tight">12-month overview</h1>
      </GlassCard>

      {/* KPI cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {kpis.map((k, i) => (
          <GlassCard key={k.label} delay={i * 0.05 + 0.05} className="flex items-center gap-4">
            <div
              className="w-12 h-12 rounded-[14px] flex items-center justify-center text-white shrink-0"
              style={{ background: k.accent }}
            >
              <k.Icon className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">{k.label}</p>
              <p className={`font-mono text-xl font-bold tabular-nums tracking-tight ${k.color}`}>{k.value}</p>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Chart */}
      <GlassCard delay={0.2}>
        <div className="flex items-center justify-between mb-5">
          <div>
            <p className="text-[15px] font-semibold">Income vs Expenses</p>
            <p className="text-xs text-muted-foreground mt-0.5">Last 12 months</p>
          </div>
          <div className="flex gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-gain" />
              <span className="text-muted-foreground">Income</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm bg-loss" />
              <span className="text-muted-foreground">Expenses</span>
            </div>
          </div>
        </div>
        <div className="h-72">
          {cashflow.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <p className="text-sm text-muted-foreground">No data yet. Import transactions to see cash flow.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cashflow}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="transparent" />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} stroke="transparent" />
                <Tooltip
                  formatter={(v) => formatCurrency(Number(v))}
                  contentStyle={{
                    background: "var(--color-card)",
                    border: "1px solid var(--color-border)",
                    borderRadius: 12,
                    fontSize: 13,
                  }}
                />
                <Legend />
                <Bar dataKey="income" fill="var(--color-chart-2)" name="Income" radius={[4, 4, 0, 0]} />
                <Bar dataKey="expenses" fill="var(--color-chart-4)" name="Expenses" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </GlassCard>

      {/* Recurring Expenses */}
      <GlassCard delay={0.3}>
        <h2 className="text-[15px] font-semibold mb-4">Recurring Expenses</h2>
        {recurring.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">No recurring expenses tracked yet.</p>
        ) : (
          <div className="divide-y divide-border">
            {recurring.map((r) => (
              <div
                key={r.id}
                className={`flex items-center justify-between py-3.5 ${!r.active ? "opacity-50" : ""}`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-[11px] bg-accent flex items-center justify-center text-muted-foreground shrink-0">
                    <RefreshCw className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{r.name}</p>
                    <p className="text-xs text-muted-foreground capitalize mt-0.5">{r.frequency} · Next: {r.next_due_date}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm font-bold tabular-nums text-loss">
                    {formatCurrency(r.amount, r.currency)}
                  </span>
                  {!r.active && (
                    <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded-lg bg-accent text-muted-foreground">
                      Paused
                    </span>
                  )}
                  {r.active && (
                    <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded-lg bg-gain/10 text-gain">
                      Active
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
