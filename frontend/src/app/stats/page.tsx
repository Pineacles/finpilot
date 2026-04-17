"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, MonthlyStats, YearlyStats, TransactionItem } from "@/lib/api";
import { formatCurrency, formatPct, formatDate } from "@/lib/format";
import { GlassCard } from "@/components/glass-card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
  PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";
import {
  ChevronLeft, ChevronRight, Calendar, Wallet, PiggyBank, Receipt, Store, CreditCard,
  ArrowUpRight, ArrowDownRight, Minus, TrendingUp,
} from "lucide-react";
import { useRouter } from "next/navigation";

const CHART_COLORS = [
  "var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)",
  "#f97316", "#ec4899", "#06b6d4", "#8b5cf6", "#84cc16",
  "#e11d48", "#14b8a6", "#d946ef", "#0ea5e9", "#fb923c", "#6366f1",
];

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ─── KPI icon badge accents ────────────────────────────────────────────────
const KPI_ACCENTS = [
  "linear-gradient(135deg, #16a34a, #22c55e)",  // Income   – green
  "linear-gradient(135deg, #dc2626, #ef4444)",  // Expenses – red
  "linear-gradient(135deg, #2f5bff, #8b5cf6)",  // Net      – blue/purple
  "linear-gradient(135deg, #f59e0b, #fb923c)",  // Daily    – amber
];

// ─── Change badge ──────────────────────────────────────────────────────────
function Change({ value, pct, expense = false }: { value: number; pct: number; expense?: boolean }) {
  if (Math.abs(pct) < 0.5)
    return (
      <span className="text-[12px] text-muted-foreground flex items-center gap-1">
        <Minus className="h-3 w-3" />No change
      </span>
    );
  const up = value > 0;
  const good = expense ? !up : up;
  return (
    <span className={`text-[13px] flex items-center gap-1 font-semibold ${good ? "text-gain" : "text-loss"}`}>
      {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
      {formatCurrency(Math.abs(value))} ({formatPct(pct)})
    </span>
  );
}

// ─── Category drill-down modal ─────────────────────────────────────────────
function CategoryDrillDown({
  open, onClose, categoryName, categoryId, fromDate, toDate,
}: {
  open: boolean; onClose: () => void; categoryName: string;
  categoryId: string | null; fromDate: string; toDate: string;
}) {
  const router = useRouter();
  const [txns, setTxns] = useState<TransactionItem[]>([]);
  const [ld, setLd] = useState(false);

  useEffect(() => {
    if (!open || !categoryId) return;
    setLd(true);
    api.transactions({ category_id: categoryId, from_date: fromDate, to_date: toDate, limit: 500 })
      .then(setTxns)
      .finally(() => setLd(false));
  }, [open, categoryId, fromDate, toDate]);

  const total = txns.reduce((s, t) => s + Math.abs(t.amount), 0);

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col rounded-3xl glass border-border/60">
        <DialogHeader>
          <DialogTitle className="text-lg font-bold">{categoryName}</DialogTitle>
          <p className="text-[13px] text-muted-foreground">
            {fromDate} → {toDate} &mdash; {txns.length} transactions &mdash; Total: <span className="font-semibold text-foreground">{formatCurrency(total)}</span>
          </p>
        </DialogHeader>
        <div className="overflow-y-auto flex-1 -mx-6 px-6">
          {ld ? (
            <p className="text-muted-foreground py-4">Loading…</p>
          ) : txns.length === 0 ? (
            <p className="text-muted-foreground py-4">No transactions found.</p>
          ) : (
            <table className="w-full text-[14px]">
              <thead>
                <tr className="border-b text-left text-muted-foreground text-[12px] uppercase tracking-wide">
                  <th className="pb-2 font-semibold">Date</th>
                  <th className="pb-2 font-semibold">Merchant</th>
                  <th className="pb-2 font-semibold text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {txns.map(t => (
                  <tr
                    key={t.id}
                    className="border-b border-border/40 cursor-pointer hover:bg-accent/40 transition-colors"
                    onClick={() => router.push(`/transactions?highlight=${t.id}`)}
                  >
                    <td className="py-2 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td>
                    <td className="py-2 font-medium">{t.merchant}</td>
                    <td className={`py-2 text-right font-semibold tabular-nums ${t.amount < 0 ? "text-loss" : "text-gain"}`}>
                      {formatCurrency(t.amount, t.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Card section header ───────────────────────────────────────────────────
function SectionHeader({ eyebrow, title, icon: Icon }: { eyebrow: string; title: string; icon?: React.ElementType }) {
  return (
    <div className="mb-5">
      <p className="text-[11px] font-semibold text-primary uppercase tracking-wider mb-1">{eyebrow}</p>
      <h2 className="text-[17px] font-bold tracking-tight flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
        {title}
      </h2>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────
export default function StatsPage() {
  const today = new Date();
  const [tab, setTab] = useState("monthly");
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [monthly, setMonthly] = useState<MonthlyStats | null>(null);
  const [yearly, setYearly] = useState<YearlyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [drillCat, setDrillCat] = useState<{ id: string | null; name: string } | null>(null);

  useEffect(() => {
    setLoading(true);
    if (tab === "monthly")
      api.monthlyStats(year, month).then(setMonthly).finally(() => setLoading(false));
    else
      api.yearlyStats(year).then(setYearly).finally(() => setLoading(false));
  }, [tab, year, month]);

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(year - 1); } else setMonth(month - 1); };
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(year + 1); } else setMonth(month + 1); };

  return (
    <div className="space-y-7">
      {/* ── Controls bar ── */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-center justify-end flex-wrap gap-4"
      >
        <div className="flex items-center gap-3">
          {/* Tab switcher — glass pill style (matches RangeSwitcher) */}
          <div className="flex items-center gap-1 p-1 glass bg-card rounded-[14px]">
            {["monthly", "yearly"].map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-1.5 rounded-[10px] text-[13px] font-semibold transition-all duration-150 cursor-pointer capitalize ${
                  tab === t
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Date navigation */}
          <div className="flex items-center gap-2">
            <button
              onClick={tab === "monthly" ? prevMonth : () => setYear(year - 1)}
              className="h-9 w-9 rounded-[12px] glass bg-card flex items-center justify-center cursor-pointer hover:bg-accent transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-[14px] font-semibold w-28 text-center tabular-nums">
              {tab === "monthly" ? `${MONTHS[month - 1]} ${year}` : String(year)}
            </span>
            <button
              onClick={tab === "monthly" ? nextMonth : () => setYear(year + 1)}
              className="h-9 w-9 rounded-[12px] glass bg-card flex items-center justify-center cursor-pointer hover:bg-accent transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </motion.div>

      {/* ── Loading skeleton ── */}
      {loading ? (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-[120px] rounded-[24px] bg-muted animate-pulse" />
          ))}
        </div>
      ) : tab === "monthly" && monthly ? (
        <MonthlyView
          monthly={monthly}
          drillCat={drillCat}
          setDrillCat={setDrillCat}
        />
      ) : tab === "yearly" && yearly ? (
        <YearlyView yearly={yearly} />
      ) : (
        <div className="h-64 rounded-[24px] bg-muted animate-pulse" />
      )}
    </div>
  );
}

// ─── Monthly view ──────────────────────────────────────────────────────────
function MonthlyView({
  monthly,
  drillCat,
  setDrillCat,
}: {
  monthly: MonthlyStats;
  drillCat: { id: string | null; name: string } | null;
  setDrillCat: (v: { id: string | null; name: string } | null) => void;
}) {
  const s = monthly.summary;
  const totalForPie = monthly.categories.reduce((sum, c) => sum + c.total, 0);

  const kpiCards = [
    { l: "Income",       v: formatCurrency(s.income),          color: "text-gain",  cmp: monthly.comparison.income,   expense: false, icon: Wallet,   accent: KPI_ACCENTS[0] },
    { l: "Expenses",     v: formatCurrency(s.expenses),        color: "text-loss",  cmp: monthly.comparison.expenses, expense: true,  icon: Receipt,  accent: KPI_ACCENTS[1] },
    { l: "Net / Saved",  v: formatCurrency(s.net),             color: s.net >= 0 ? "text-gain" : "text-loss", cmp: monthly.comparison.net, expense: false, icon: PiggyBank, accent: KPI_ACCENTS[2] },
    { l: "Daily Average",v: formatCurrency(s.avg_daily_spend), color: "",           sub: `${s.txn_count} transactions`, icon: Calendar, accent: KPI_ACCENTS[3] },
  ];

  return (
    <>
      {/* KPI cards */}
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {kpiCards.map((k, i) => (
          <GlassCard key={k.l} delay={0.05 + i * 0.04} className="relative overflow-hidden">
            {/* Glow blob */}
            <div
              className="absolute -top-10 -right-10 w-36 h-36 rounded-full opacity-30 pointer-events-none"
              style={{ background: k.accent, filter: "blur(36px)" }}
            />
            {/* Icon badge */}
            <div className="flex items-center justify-between mb-4 relative z-10">
              <div
                className="w-10 h-10 rounded-[12px] flex items-center justify-center text-white"
                style={{ background: k.accent }}
              >
                <k.icon className="h-[18px] w-[18px]" />
              </div>
            </div>
            <p className="text-[12px] text-muted-foreground font-medium mb-1 relative z-10">{k.l}</p>
            <p className={`font-mono tabular-nums text-[28px] font-bold leading-none mb-2 relative z-10 ${k.color}`} style={{letterSpacing: '-0.8px'}}>{k.v}</p>
            <div className="relative z-10">
              {("cmp" in k) && k.cmp && (
                <Change value={(k.cmp as { change: number; change_pct: number }).change} pct={(k.cmp as { change: number; change_pct: number }).change_pct} expense={k.expense} />
              )}
              {("sub" in k) && k.sub && <span className="text-[12px] text-muted-foreground">{k.sub as string}</span>}
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Category donut + breakdown */}
      <div className="grid gap-[18px]" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <GlassCard delay={0.15}>
          <SectionHeader eyebrow="Breakdown" title="Spending by Category" />
          {monthly.categories.length === 0 ? (
            <p className="text-muted-foreground text-[14px]">No data.</p>
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={monthly.categories}
                    dataKey="total"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    innerRadius={55}
                    onClick={(entry: { id?: string; name?: string }) => setDrillCat({ id: entry.id ?? null, name: entry.name ?? "" })}
                    style={{ cursor: "pointer" }}
                  >
                    {monthly.categories.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: unknown) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </GlassCard>

        <GlassCard delay={0.2}>
          <SectionHeader eyebrow="Categories" title="Category Breakdown" />
          <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
            {monthly.categories.map((c, i) => {
              const pct = totalForPie ? (c.total / totalForPie) * 100 : 0;
              return (
                <div
                  key={c.name}
                  className="cursor-pointer hover:bg-accent/50 rounded-xl p-2 -mx-2 transition-colors"
                  onClick={() => setDrillCat({ id: c.id, name: c.name })}
                >
                  <div className="flex items-center justify-between text-[13px] mb-1.5">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-[3px]"
                        style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                      />
                      <span className="font-medium">{c.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground text-[12px]">{c.count} txns</span>
                      <span className="font-semibold tabular-nums">{formatCurrency(c.total)}</span>
                    </div>
                  </div>
                  <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.6, delay: 0.3 + i * 0.03 }}
                      className="h-full rounded-full"
                      style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      </div>

      {/* Spending pace + Fixed vs Variable */}
      <div className="grid gap-5 lg:grid-cols-2">
        <GlassCard delay={0.25}>
          <SectionHeader eyebrow="Trend" title="Spending Pace" icon={TrendingUp} />
          <div className="h-64">
            {monthly.spending_velocity.length === 0 ? (
              <p className="text-muted-foreground text-[14px]">No data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={monthly.spending_velocity}>
                  <defs>
                    <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11 }}
                    tickFormatter={d => d.slice(8)}
                    stroke="var(--muted-foreground)"
                  />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    tickFormatter={v => `${(v / 1000).toFixed(1)}k`}
                    stroke="var(--muted-foreground)"
                  />
                  <Tooltip formatter={(v: unknown) => formatCurrency(Number(v))} />
                  <Area
                    type="monotone"
                    dataKey="cumulative"
                    stroke="var(--chart-1)"
                    fill="url(#spendGrad)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlassCard>

        <GlassCard delay={0.3}>
          <SectionHeader eyebrow="Allocation" title="Fixed vs Variable" />
          <div className="space-y-6 pt-2">
            {[
              { l: "Recurring / Fixed", v: monthly.recurring_vs_discretionary.recurring, color: "bg-primary" },
              { l: "Discretionary",     v: monthly.recurring_vs_discretionary.discretionary, color: "bg-[var(--chart-3)]" },
            ].map(item => (
              <div key={item.l}>
                <div className="flex justify-between text-[13px] mb-2">
                  <span className="font-medium">{item.l}</span>
                  <span className="font-semibold tabular-nums">{formatCurrency(item.v)}</span>
                </div>
                <div className="h-2.5 rounded-full bg-secondary overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${item.color}`}
                    style={{ width: `${s.expenses ? (item.v / s.expenses) * 100 : 0}%` }}
                  />
                </div>
              </div>
            ))}
            <p className="text-[12px] text-muted-foreground pt-1">
              {s.expenses ? ((monthly.recurring_vs_discretionary.recurring / s.expenses) * 100).toFixed(0) : 0}% of spending is fixed costs
            </p>
          </div>
        </GlassCard>
      </div>

      {/* Account breakdown */}
      {monthly.account_breakdown?.length > 0 && (
        <GlassCard delay={0.35}>
          <SectionHeader eyebrow="Accounts" title="Spending by Account" icon={CreditCard} />
          <div className="grid gap-4 md:grid-cols-2">
            {monthly.account_breakdown.map(a => (
              <div key={a.name} className="flex items-center justify-between p-4 rounded-2xl bg-accent/60">
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${a.type === "credit_card" ? "bg-[var(--chart-3)]" : "bg-[var(--chart-1)]"}`} />
                  <div>
                    <p className="text-[14px] font-semibold">{a.name}</p>
                    <p className="text-[12px] text-muted-foreground">{a.count} transactions</p>
                  </div>
                </div>
                <p className="text-[15px] font-bold tabular-nums">{formatCurrency(a.total)}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Top merchants + Budget vs Actual */}
      <div className="grid gap-5 lg:grid-cols-2">
        <GlassCard delay={0.4}>
          <SectionHeader eyebrow="Merchants" title="Top Merchants" icon={Store} />
          {monthly.top_merchants.length === 0 ? (
            <p className="text-muted-foreground text-[14px]">No data.</p>
          ) : (
            <div className="space-y-3">
              {monthly.top_merchants.map((m, i) => (
                <div key={m.merchant} className="flex items-center justify-between py-1">
                  <div className="flex items-center gap-3">
                    <span className="text-muted-foreground w-5 text-right text-[12px] font-medium tabular-nums">{i + 1}.</span>
                    <span className="text-[14px] font-medium">{m.merchant}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="rounded-[8px] text-[11px] font-semibold">{m.count}×</Badge>
                    <span className="font-semibold text-[14px] tabular-nums">{formatCurrency(m.total)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard delay={0.45}>
          <SectionHeader eyebrow="Budget" title="Budget vs Actual" />
          {monthly.budget_vs_actual.length === 0 ? (
            <p className="text-muted-foreground text-[14px]">No budgets configured.</p>
          ) : (
            <div className="space-y-4">
              {monthly.budget_vs_actual.map(b => (
                <div key={b.name}>
                  <div className="flex justify-between text-[13px] mb-1.5">
                    <span className="font-medium">{b.name}</span>
                    <span className={`tabular-nums ${b.pct > 100 ? "text-loss font-semibold" : "text-muted-foreground"}`}>
                      {formatCurrency(b.spent)} / {formatCurrency(b.budget)}
                    </span>
                  </div>
                  <div className="h-2.5 rounded-full bg-secondary overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${b.pct > 100 ? "bg-loss" : "bg-primary"}`}
                      style={{ width: `${Math.min(b.pct, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      {/* Drill-down modal */}
      {drillCat && (
        <CategoryDrillDown
          open={!!drillCat}
          onClose={() => setDrillCat(null)}
          categoryName={drillCat.name}
          categoryId={drillCat.id}
          fromDate={monthly.period.start}
          toDate={monthly.period.end}
        />
      )}
    </>
  );
}

// ─── Yearly view ───────────────────────────────────────────────────────────
function YearlyView({ yearly }: { yearly: YearlyStats }) {
  const s = yearly.summary;
  const monthlyData = yearly.monthly.map(m => ({ ...m, name: MONTHS[m.month - 1] }));

  const kpiCards = [
    { l: "Total Income",   v: formatCurrency(s.income),    color: "text-gain",                          accent: KPI_ACCENTS[0], icon: Wallet    },
    { l: "Total Expenses", v: formatCurrency(s.expenses),  color: "text-loss",                          accent: KPI_ACCENTS[1], icon: Receipt   },
    { l: "Net Saved",      v: formatCurrency(s.net),       color: s.net >= 0 ? "text-gain" : "text-loss", accent: KPI_ACCENTS[2], icon: PiggyBank },
    { l: "Transactions",   v: String(s.txn_count),         color: "",                                   accent: KPI_ACCENTS[3], icon: Calendar  },
  ];

  return (
    <>
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {kpiCards.map((k, i) => (
          <GlassCard key={k.l} delay={0.05 + i * 0.04} className="relative overflow-hidden">
            <div
              className="absolute -top-10 -right-10 w-36 h-36 rounded-full opacity-30 pointer-events-none"
              style={{ background: k.accent, filter: "blur(36px)" }}
            />
            <div className="flex items-center justify-between mb-4 relative z-10">
              <div
                className="w-10 h-10 rounded-[12px] flex items-center justify-center text-white"
                style={{ background: k.accent }}
              >
                <k.icon className="h-[18px] w-[18px]" />
              </div>
            </div>
            <p className="text-[12px] text-muted-foreground font-medium mb-1 relative z-10">{k.l}</p>
            <p className={`font-mono tabular-nums text-[28px] font-bold leading-none relative z-10 ${k.color}`} style={{letterSpacing: '-0.8px'}}>{k.v}</p>
          </GlassCard>
        ))}
      </div>

      <GlassCard delay={0.2}>
        <SectionHeader eyebrow="Year Overview" title="Monthly Income vs Expenses" icon={TrendingUp} />
        <div className="h-80">
          {monthlyData.length === 0 ? (
            <p className="text-muted-foreground text-[14px]">No data.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickFormatter={v => `${(v / 1000).toFixed(0)}k`}
                  stroke="var(--muted-foreground)"
                />
                <Tooltip formatter={(v: unknown) => formatCurrency(Number(v))} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="income" fill="var(--chart-1)" name="Income" radius={[4, 4, 0, 0]} />
                <Bar dataKey="expenses" fill="var(--chart-4)" name="Expenses" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </GlassCard>
    </>
  );
}
