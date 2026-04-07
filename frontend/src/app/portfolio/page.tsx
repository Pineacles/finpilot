"use client";

import { useEffect, useState, useCallback } from "react";
import { api, PortfolioSummary, Position } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell,
} from "recharts";
import {
  Plus, Trash2, Pencil, X, Check, RefreshCw, BarChart3,
} from "lucide-react";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"];
const RANGES = ["1mo", "3mo", "6mo", "1y", "2y", "5y"];

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [showTrade, setShowTrade] = useState(false);
  const [tradeForm, setTradeForm] = useState({ symbol: "", type: "buy", quantity: "", price: "", currency: "USD", date: new Date().toISOString().split("T")[0], fees: "", deduct_from_cash: true });
  const [tradeError, setTradeError] = useState("");
  const [trading, setTrading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ quantity: "", avg_cost_price: "" });
  const [chartTicker, setChartTicker] = useState<string | null>(null);
  const [chartRange, setChartRange] = useState("1y");
  const [chartData, setChartData] = useState<{ date: string; close: number }[]>([]);
  const [chartLoading, setChartLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.portfolio().then(setPortfolio).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const interval = setInterval(load, 120000);
    return () => clearInterval(interval);
  }, [load]);

  const handleTrade = async () => {
    const f = tradeForm;
    if (!f.quantity || (f.type !== "deposit" && f.type !== "withdraw" && !f.symbol)) return;
    setTrading(true);
    setTradeError("");
    try {
      await api.trade({
        symbol: f.type === "deposit" || f.type === "withdraw" ? "CASH" : f.symbol.toUpperCase().trim(),
        type: f.type,
        quantity: parseFloat(f.quantity),
        price: f.price ? parseFloat(f.price) : undefined,
        currency: f.currency,
        date: f.date || undefined,
        fees: f.fees ? parseFloat(f.fees) : 0,
        deduct_from_cash: f.deduct_from_cash,
      });
      setTradeForm({ symbol: "", type: "buy", quantity: "", price: "", currency: "USD", date: new Date().toISOString().split("T")[0], fees: "", deduct_from_cash: true });
      setShowTrade(false);
      load();
    } catch (e) {
      setTradeError(e instanceof Error ? e.message : "Trade failed");
    } finally {
      setTrading(false);
    }
  };

  const handleUpdate = async (id: string) => {
    await api.updatePosition(id, {
      quantity: editForm.quantity ? parseFloat(editForm.quantity) : undefined,
      avg_cost_price: editForm.avg_cost_price ? parseFloat(editForm.avg_cost_price) : undefined,
    });
    setEditingId(null);
    load();
  };

  const handleDelete = async (id: string) => {
    await api.deletePosition(id);
    load();
  };

  const openChart = async (ticker: string, range = chartRange) => {
    setChartTicker(ticker);
    setChartRange(range);
    setChartLoading(true);
    try {
      const res = await api.priceChart(ticker, range);
      setChartData(res.data);
    } catch {
      setChartData([]);
    } finally {
      setChartLoading(false);
    }
  };

  useEffect(() => {
    if (chartTicker) openChart(chartTicker, chartRange);
  }, [chartRange]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && !portfolio) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Portfolio</h1>
        <div className="grid gap-4 md:grid-cols-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      </div>
    );
  }

  const p = portfolio;
  const pnlPositive = (p?.total_pnl ?? 0) >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Portfolio</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />Refresh
          </Button>
          <Button size="sm" onClick={() => setShowTrade(true)}>
            <Plus className="h-4 w-4 mr-1" />Trade / Deposit
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Portfolio Value</CardTitle></CardHeader>
          <CardContent><p className="text-xl font-bold">{formatCurrency(p?.total_value ?? 0)}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Total Cost</CardTitle></CardHeader>
          <CardContent><p className="text-xl font-bold text-muted-foreground">{formatCurrency(p?.total_cost ?? 0)}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Unrealized P&L</CardTitle></CardHeader>
          <CardContent>
            <p className={`text-xl font-bold ${pnlPositive ? "text-green-500" : "text-red-500"}`}>{formatCurrency(p?.total_pnl ?? 0)}</p>
            <p className={`text-xs ${pnlPositive ? "text-green-500" : "text-red-500"}`}>{formatPct(p?.total_pnl_pct ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Cash (Uninvested)</CardTitle></CardHeader>
          <CardContent>
            <p className="text-xl font-bold">{formatCurrency(p?.cash_balance ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1"><CardTitle className="text-xs text-muted-foreground">Positions</CardTitle></CardHeader>
          <CardContent><p className="text-xl font-bold">{p?.positions_count ?? 0}</p></CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Allocation Pie */}
        <Card>
          <CardHeader><CardTitle className="text-base">Allocation</CardTitle></CardHeader>
          <CardContent className="h-72">
            {(p?.positions.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">No positions yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={p!.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%" outerRadius={90} innerRadius={50}
                    label={((entry: { symbol: string; weight_pct: number }) => `${entry.symbol} ${entry.weight_pct.toFixed(0)}%`) as unknown as boolean}>
                    {p!.positions.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Positions Table */}
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle className="text-base">Positions</CardTitle></CardHeader>
          <CardContent>
            {(p?.positions.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">No positions. Click "Add Position" to get started.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 font-medium">Ticker</th>
                      <th className="pb-2 font-medium">Qty</th>
                      <th className="pb-2 font-medium text-right">Price</th>
                      <th className="pb-2 font-medium text-right">Day</th>
                      <th className="pb-2 font-medium text-right">Value</th>
                      <th className="pb-2 font-medium text-right">P&L</th>
                      <th className="pb-2 w-20"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {p!.positions.map((pos) => (
                      editingId === pos.id ? (
                        <tr key={pos.id} className="border-b bg-primary/5">
                          <td className="py-2 font-bold">{pos.symbol}</td>
                          <td className="py-2"><Input value={editForm.quantity} onChange={(e) => setEditForm({ ...editForm, quantity: e.target.value })} className="h-7 w-20 text-sm" /></td>
                          <td className="py-2 text-right"><Input value={editForm.avg_cost_price} onChange={(e) => setEditForm({ ...editForm, avg_cost_price: e.target.value })} className="h-7 w-24 text-sm text-right" placeholder="Avg price" /></td>
                          <td colSpan={2}></td>
                          <td colSpan={2} className="py-2 text-right">
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => handleUpdate(pos.id)}><Check className="h-3 w-3 text-green-500" /></Button>
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditingId(null)}><X className="h-3 w-3" /></Button>
                          </td>
                        </tr>
                      ) : (
                        <tr key={pos.id} className="border-b border-border/50 hover:bg-accent/30 cursor-pointer" onClick={() => openChart(pos.symbol)}>
                          <td className="py-2">
                            <div>
                              <span className="font-bold">{pos.symbol}</span>
                              <span className="text-xs text-muted-foreground ml-1 hidden md:inline">{pos.name}</span>
                            </div>
                            {pos.first_bought && (
                              <span className="text-[10px] text-muted-foreground">Since {pos.first_bought.split("T")[0]}</span>
                            )}
                          </td>
                          <td className="py-2">{pos.quantity}</td>
                          <td className="py-2 text-right">{pos.last_price?.toFixed(2) ?? "-"}</td>
                          <td className={`py-2 text-right text-xs ${pos.change >= 0 ? "text-green-500" : "text-red-500"}`}>
                            {pos.change >= 0 ? "+" : ""}{pos.change.toFixed(2)} ({pos.change_pct >= 0 ? "+" : ""}{pos.change_pct.toFixed(1)}%)
                          </td>
                          <td className="py-2 text-right font-medium">{formatCurrency(pos.market_value)}</td>
                          <td className={`py-2 text-right text-xs ${pos.unrealized_pnl >= 0 ? "text-green-500" : "text-red-500"}`}>
                            {formatCurrency(pos.unrealized_pnl)} ({pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(1)}%)
                          </td>
                          <td className="py-2 text-right" onClick={(e) => e.stopPropagation()}>
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => { setEditingId(pos.id); setEditForm({ quantity: String(pos.quantity), avg_cost_price: String(pos.avg_cost_price) }); }}>
                              <Pencil className="h-3 w-3 text-muted-foreground" />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => handleDelete(pos.id)}>
                              <Trash2 className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          </td>
                        </tr>
                      )
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Trade Dialog */}
      <Dialog open={showTrade} onOpenChange={setShowTrade}>
        <DialogContent>
          <DialogHeader><DialogTitle>Record Trade</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">Type</label>
              <div className="grid grid-cols-4 gap-1">
                {(["buy", "sell", "deposit", "withdraw"] as const).map((t) => (
                  <Button key={t} variant={tradeForm.type === t ? "default" : "outline"} size="sm" onClick={() => setTradeForm({ ...tradeForm, type: t })} className="capitalize">
                    {t}
                  </Button>
                ))}
              </div>
            </div>
            {tradeForm.type !== "deposit" && tradeForm.type !== "withdraw" && (
              <div>
                <label className="text-xs text-muted-foreground">Ticker Symbol</label>
                <Input placeholder="AAPL, NVDA, NESN.SW, BTC-USD..." value={tradeForm.symbol} onChange={(e) => setTradeForm({ ...tradeForm, symbol: e.target.value })} />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">{tradeForm.type === "deposit" || tradeForm.type === "withdraw" ? "Amount" : "Quantity"}</label>
                <Input type="number" placeholder={tradeForm.type === "deposit" ? "5000" : "10"} value={tradeForm.quantity} onChange={(e) => setTradeForm({ ...tradeForm, quantity: e.target.value })} />
              </div>
              {tradeForm.type !== "deposit" && tradeForm.type !== "withdraw" && (
                <div>
                  <label className="text-xs text-muted-foreground">Price per share (empty = market)</label>
                  <Input type="number" placeholder="150.00" value={tradeForm.price} onChange={(e) => setTradeForm({ ...tradeForm, price: e.target.value })} />
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Date</label>
                <Input type="date" value={tradeForm.date} onChange={(e) => setTradeForm({ ...tradeForm, date: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Currency</label>
                <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={tradeForm.currency} onChange={(e) => setTradeForm({ ...tradeForm, currency: e.target.value })}>
                  <option value="USD">USD</option>
                  <option value="CHF">CHF</option>
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                  <option value="KRW">KRW</option>
                </select>
              </div>
            </div>
            {tradeForm.type === "buy" && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={tradeForm.deduct_from_cash} onChange={(e) => setTradeForm({ ...tradeForm, deduct_from_cash: e.target.checked })} />
                Deduct from cash balance
              </label>
            )}
            {tradeForm.type === "sell" && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={tradeForm.deduct_from_cash} onChange={(e) => setTradeForm({ ...tradeForm, deduct_from_cash: e.target.checked })} />
                Add proceeds to cash balance
              </label>
            )}
            {tradeError && <p className="text-xs text-red-500">{tradeError}</p>}
            <Button onClick={handleTrade} disabled={trading} className="w-full capitalize">{trading ? "Processing..." : tradeForm.type}</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Price Chart Dialog */}
      <Dialog open={!!chartTicker} onOpenChange={(v) => { if (!v) setChartTicker(null); }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              {chartTicker}
              {chartData.length > 0 && (
                <span className="text-sm font-normal text-muted-foreground ml-2">
                  {chartData[0].date} — {chartData[chartData.length - 1].date}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex gap-1 mb-2">
            {RANGES.map((r) => (
              <Button key={r} variant={chartRange === r ? "default" : "ghost"} size="sm" className="h-7 text-xs" onClick={() => setChartRange(r)}>
                {r.replace("mo", "M").replace("y", "Y")}
              </Button>
            ))}
          </div>
          <div className="h-80">
            {chartLoading ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>
            ) : chartData.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data available.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v) => Number(v).toFixed(2)} labelFormatter={(l) => l} />
                  <Line type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
