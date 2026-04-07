"use client";

import { useEffect, useState } from "react";
import { api, MonthlyStats, YearlyStats, TransactionItem } from "@/lib/api";
import { formatCurrency, formatPct, formatDate } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  AreaChart,
  Area,
} from "recharts";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  ChevronLeft,
  ChevronRight,
  Calendar,
  Wallet,
  PiggyBank,
  Receipt,
  Store,
  CreditCard,
} from "lucide-react";
import { useRouter } from "next/navigation";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#a855f7"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function CategoryDrillDown({ open, onClose, categoryName, categoryId, fromDate, toDate }: {
  open: boolean;
  onClose: () => void;
  categoryName: string;
  categoryId: string | null;
  fromDate: string;
  toDate: string;
}) {
  const router = useRouter();
  const [txns, setTxns] = useState<TransactionItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !categoryId) return;
    setLoading(true);
    api.transactions({ category_id: categoryId, from_date: fromDate, to_date: toDate, limit: 500 })
      .then(setTxns)
      .finally(() => setLoading(false));
  }, [open, categoryId, fromDate, toDate]);

  const total = txns.reduce((s, t) => s + Math.abs(t.amount), 0);

  const goToTransaction = (txnId: string) => {
    router.push(`/transactions?highlight=${txnId}`);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{categoryName} — {txns.length} transactions</DialogTitle>
          <p className="text-sm text-muted-foreground">{fromDate} to {toDate} — Total: {formatCurrency(total)}</p>
        </DialogHeader>
        <div className="overflow-y-auto flex-1 -mx-6 px-6">
          {loading ? (
            <p className="text-sm text-muted-foreground py-4">Loading...</p>
          ) : txns.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No transactions found.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Merchant</th>
                  <th className="pb-2 font-medium">Description</th>
                  <th className="pb-2 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {txns.map((t) => (
                  <tr key={t.id} className="border-b border-border/50 cursor-pointer hover:bg-accent/50 transition-colors" onClick={() => goToTransaction(t.id)}>
                    <td className="py-1.5 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td>
                    <td className="py-1.5 font-medium">{t.merchant}</td>
                    <td className="py-1.5 max-w-[200px]">
                      {t.notes ? (
                        <span className="text-xs text-muted-foreground truncate block" title={t.notes}>
                          {t.notes.split("|")[0].trim().substring(0, 50)}
                        </span>
                      ) : <span className="text-xs text-muted-foreground">-</span>}
                    </td>
                    <td className={`py-1.5 text-right font-medium whitespace-nowrap ${t.amount < 0 ? "text-red-500" : "text-green-500"}`}>
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

function ChangeIndicator({ value, pct }: { value: number; pct: number }) {
  if (Math.abs(pct) < 0.5) return <span className="text-xs text-muted-foreground flex items-center gap-1"><Minus className="h-3 w-3" />No change</span>;
  const up = value > 0;
  return (
    <span className={`text-xs flex items-center gap-1 ${up ? "text-green-500" : "text-red-500"}`}>
      {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
      {formatCurrency(Math.abs(value))} ({formatPct(pct)})
    </span>
  );
}

function ExpenseChangeIndicator({ value, pct }: { value: number; pct: number }) {
  if (Math.abs(pct) < 0.5) return <span className="text-xs text-muted-foreground flex items-center gap-1"><Minus className="h-3 w-3" />No change</span>;
  const up = value > 0;
  return (
    <span className={`text-xs flex items-center gap-1 ${up ? "text-red-500" : "text-green-500"}`}>
      {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
      {formatCurrency(Math.abs(value))} ({formatPct(pct)})
    </span>
  );
}

export default function StatsPage() {
  const today = new Date();
  const [tab, setTab] = useState("monthly");
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [monthly, setMonthly] = useState<MonthlyStats | null>(null);
  const [yearly, setYearly] = useState<YearlyStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    if (tab === "monthly") {
      api.monthlyStats(year, month).then(setMonthly).finally(() => setLoading(false));
    } else {
      api.yearlyStats(year).then(setYearly).finally(() => setLoading(false));
    }
  }, [tab, year, month]);

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else setMonth(month - 1);
  };
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else setMonth(month + 1);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Statistics</h1>

      <Tabs value={tab} onValueChange={setTab}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="monthly"><Calendar className="h-4 w-4 mr-1" />Monthly</TabsTrigger>
            <TabsTrigger value="yearly"><Calendar className="h-4 w-4 mr-1" />Yearly</TabsTrigger>
          </TabsList>

          {/* Period navigation */}
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={tab === "monthly" ? prevMonth : () => setYear(year - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium w-28 text-center">
              {tab === "monthly" ? `${MONTH_NAMES[month - 1]} ${year}` : String(year)}
            </span>
            <Button variant="ghost" size="icon" onClick={tab === "monthly" ? nextMonth : () => setYear(year + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="space-y-4 mt-4"><Skeleton className="h-32" /><Skeleton className="h-64" /><Skeleton className="h-64" /></div>
        ) : (
          <>
            {/* ─── MONTHLY TAB ─── */}
            <TabsContent value="monthly" className="space-y-6 mt-4">
              {monthly && <MonthlyView data={monthly} year={year} month={month} />}
            </TabsContent>

            {/* ─── YEARLY TAB ─── */}
            <TabsContent value="yearly" className="space-y-6 mt-4">
              {yearly && <YearlyView data={yearly} />}
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
}

function MonthlyView({ data, year, month }: { data: MonthlyStats; year: number; month: number }) {
  const [drillCat, setDrillCat] = useState<{ id: string | null; name: string } | null>(null);
  const s = data.summary;
  const recDisc = data.recurring_vs_discretionary;
  const totalForPie = data.categories.reduce((sum, c) => sum + c.total, 0);

  return (
    <>
      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3 w-3" />Income</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-green-500">{formatCurrency(s.income)}</p>
            {data.comparison.income && <ChangeIndicator value={data.comparison.income.change} pct={data.comparison.income.change_pct} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground flex items-center gap-1"><Receipt className="h-3 w-3" />Expenses</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-red-500">{formatCurrency(s.expenses)}</p>
            {data.comparison.expenses && <ExpenseChangeIndicator value={data.comparison.expenses.change} pct={data.comparison.expenses.change_pct} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground flex items-center gap-1"><PiggyBank className="h-3 w-3" />Net / Saved</CardTitle></CardHeader>
          <CardContent>
            <p className={`text-xl font-bold ${s.net >= 0 ? "text-green-500" : "text-red-500"}`}>{formatCurrency(s.net)}</p>
            <span className="text-xs text-muted-foreground">{s.savings_rate.toFixed(1)}% savings rate</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Daily Average</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold">{formatCurrency(s.avg_daily_spend)}</p>
            <span className="text-xs text-muted-foreground">{s.txn_count} transactions</span>
          </CardContent>
        </Card>
      </div>

      {/* Spending by Category + Recurring vs Discretionary */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Spending by Category</CardTitle></CardHeader>
          <CardContent className="h-72">
            {data.categories.length === 0 ? (
              <p className="text-sm text-muted-foreground">No spending data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.categories} dataKey="total" nameKey="name" cx="50%" cy="50%" outerRadius={90} innerRadius={50}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}>
                    {data.categories.map((c, i) => <Cell key={i} fill={c.color || COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Category Breakdown</CardTitle></CardHeader>
          <CardContent>
            {data.categories.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data.</p>
            ) : (
              <div className="space-y-3 max-h-72 overflow-y-auto">
                {data.categories.map((c, i) => {
                  const pct = totalForPie ? (c.total / totalForPie) * 100 : 0;
                  return (
                    <div key={c.name} className="cursor-pointer hover:bg-accent/50 rounded-lg p-1.5 -mx-1.5 transition-colors" onClick={() => setDrillCat({ id: c.id, name: c.name })}>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: c.color || COLORS[i % COLORS.length] }} />
                          <span>{c.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground text-xs">{c.count} txns</span>
                          <span className="font-medium">{formatCurrency(c.total)}</span>
                        </div>
                      </div>
                      <Progress value={pct} className="h-1.5" />
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Spending Velocity + Recurring vs Discretionary */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Spending Pace</CardTitle></CardHeader>
          <CardContent className="h-64">
            {data.spending_velocity.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.spending_velocity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(8)} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} labelFormatter={(l) => `Day ${l.slice(8)}`} />
                  <Area type="monotone" dataKey="cumulative" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Fixed vs Variable</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-6 pt-4">
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span>Recurring / Fixed</span>
                  <span className="font-medium">{formatCurrency(recDisc.recurring)}</span>
                </div>
                <Progress value={s.expenses ? (recDisc.recurring / s.expenses) * 100 : 0} className="h-3 [&>div]:bg-blue-500" />
              </div>
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span>Discretionary</span>
                  <span className="font-medium">{formatCurrency(recDisc.discretionary)}</span>
                </div>
                <Progress value={s.expenses ? (recDisc.discretionary / s.expenses) * 100 : 0} className="h-3 [&>div]:bg-orange-500" />
              </div>
              <p className="text-xs text-muted-foreground">
                {s.expenses ? ((recDisc.recurring / s.expenses) * 100).toFixed(0) : 0}% of spending is fixed costs
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Account Breakdown (Debit vs Credit Card) */}
      {data.account_breakdown && data.account_breakdown.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-1"><CreditCard className="h-4 w-4" />Spending by Account</CardTitle></CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              {data.account_breakdown.map((a) => (
                <div key={a.name} className="flex items-center justify-between p-3 rounded-lg border">
                  <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${a.type === "credit_card" ? "bg-orange-500" : "bg-blue-500"}`} />
                    <div>
                      <p className="text-sm font-medium">{a.name}</p>
                      <p className="text-xs text-muted-foreground">{a.count} transactions</p>
                    </div>
                  </div>
                  <p className="text-sm font-bold">{formatCurrency(a.total)}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Merchants + Budget vs Actual */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base flex items-center gap-1"><Store className="h-4 w-4" />Top Merchants</CardTitle></CardHeader>
          <CardContent>
            {data.top_merchants.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data.</p>
            ) : (
              <div className="space-y-2">
                {data.top_merchants.map((m, i) => (
                  <div key={m.merchant} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                      <span>{m.merchant}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-xs">{m.count}x</Badge>
                      <span className="font-medium">{formatCurrency(m.total)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Budget vs Actual</CardTitle></CardHeader>
          <CardContent>
            {data.budget_vs_actual.length === 0 ? (
              <p className="text-sm text-muted-foreground">No budgets set.</p>
            ) : (
              <div className="space-y-4">
                {data.budget_vs_actual.map((b) => (
                  <div key={b.name}>
                    <div className="flex justify-between text-sm mb-1">
                      <span>{b.name}</span>
                      <span className={b.pct > 100 ? "text-red-500 font-medium" : "text-muted-foreground"}>
                        {formatCurrency(b.spent)} / {formatCurrency(b.budget)}
                      </span>
                    </div>
                    <Progress value={Math.min(b.pct, 100)} className={b.pct > 100 ? "[&>div]:bg-red-500" : ""} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {drillCat && (
        <CategoryDrillDown
          open={!!drillCat}
          onClose={() => setDrillCat(null)}
          categoryName={drillCat.name}
          categoryId={drillCat.id}
          fromDate={data.period.start}
          toDate={data.period.end}
        />
      )}
    </>
  );
}

function YearlyView({ data }: { data: YearlyStats }) {
  const [drillCat, setDrillCat] = useState<{ id: string | null; name: string } | null>(null);
  const s = data.summary;
  const monthlyData = data.monthly.map((m) => ({
    ...m,
    name: MONTH_NAMES[m.month - 1],
  }));

  // Transform category trends for line chart
  const trendCategories = [...new Set(data.category_trends.map((t) => t.category))];
  const trendData = Array.from({ length: 12 }, (_, i) => {
    const row: Record<string, number | string> = { name: MONTH_NAMES[i] };
    trendCategories.forEach((cat) => {
      const match = data.category_trends.find((t) => t.month === i + 1 && t.category === cat);
      row[cat] = match ? match.total : 0;
    });
    return row;
  });

  const totalForPie = data.categories.reduce((sum, c) => sum + c.total, 0);

  return (
    <>
      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Total Income</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-green-500">{formatCurrency(s.income)}</p>
            {data.comparison.income && <ChangeIndicator value={data.comparison.income.change} pct={data.comparison.income.change_pct} />}
            <span className="text-xs text-muted-foreground block mt-1">Avg {formatCurrency(s.avg_monthly_income)}/mo</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Total Expenses</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold text-red-500">{formatCurrency(s.expenses)}</p>
            {data.comparison.expenses && <ExpenseChangeIndicator value={data.comparison.expenses.change} pct={data.comparison.expenses.change_pct} />}
            <span className="text-xs text-muted-foreground block mt-1">Avg {formatCurrency(s.avg_monthly_spend)}/mo</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Net Saved</CardTitle></CardHeader>
          <CardContent>
            <p className={`text-xl font-bold ${s.net >= 0 ? "text-green-500" : "text-red-500"}`}>{formatCurrency(s.net)}</p>
            <span className="text-xs text-muted-foreground">{s.savings_rate.toFixed(1)}% savings rate</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Transactions</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold">{s.txn_count}</p>
            <span className="text-xs text-muted-foreground">{data.monthly.length} months of data</span>
          </CardContent>
        </Card>
      </div>

      {/* Monthly Income vs Expenses */}
      <Card>
        <CardHeader><CardTitle className="text-base">Monthly Income vs Expenses</CardTitle></CardHeader>
        <CardContent className="h-80">
          {monthlyData.length === 0 ? (
            <p className="text-sm text-muted-foreground">No data.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                <Legend />
                <Bar dataKey="income" fill="#10b981" name="Income" radius={[2, 2, 0, 0]} />
                <Bar dataKey="expenses" fill="#ef4444" name="Expenses" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Net Savings Trend + Net Worth */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Monthly Net Savings</CardTitle></CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`} />
                <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                <Bar dataKey="net" name="Net" radius={[2, 2, 0, 0]}>
                  {monthlyData.map((entry, i) => (
                    <Cell key={i} fill={entry.net >= 0 ? "#10b981" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Portfolio Value</CardTitle></CardHeader>
          <CardContent className="h-64">
            {data.net_worth_history.length === 0 ? (
              <p className="text-sm text-muted-foreground">No portfolio data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.net_worth_history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Category Breakdown + Trends */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Annual Spending by Category</CardTitle></CardHeader>
          <CardContent className="h-72">
            {data.categories.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={data.categories} dataKey="total" nameKey="name" cx="50%" cy="50%" outerRadius={90} innerRadius={50}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}>
                    {data.categories.map((c, i) => <Cell key={i} fill={c.color || COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Category Trends (Top 5)</CardTitle></CardHeader>
          <CardContent className="h-72">
            {trendCategories.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Legend />
                  {trendCategories.map((cat, i) => (
                    <Line key={cat} type="monotone" dataKey={cat} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top Merchants */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-1"><Store className="h-4 w-4" />Top Merchants ({data.period.year})</CardTitle></CardHeader>
        <CardContent>
          {data.top_merchants.length === 0 ? (
            <p className="text-sm text-muted-foreground">No data.</p>
          ) : (
            <div className="grid gap-2 md:grid-cols-2">
              {data.top_merchants.map((m, i) => (
                <div key={m.merchant} className="flex items-center justify-between text-sm py-1">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground w-5 text-right">{i + 1}.</span>
                    <span>{m.merchant}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">{m.count}x</Badge>
                    <span className="font-medium">{formatCurrency(m.total)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {drillCat && (
        <CategoryDrillDown
          open={!!drillCat}
          onClose={() => setDrillCat(null)}
          categoryName={drillCat.name}
          categoryId={drillCat.id}
          fromDate={`${data.period.year}-01-01`}
          toDate={`${data.period.year}-12-31`}
        />
      )}
    </>
  );
}
