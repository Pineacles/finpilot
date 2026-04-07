"use client";

import { useEffect, useState, useCallback } from "react";
import { api, PortfolioSummary, Position, PortfolioAnalysis, AnalysisListItem, StockAnalysis } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, PieChart, Pie, Cell,
} from "recharts";
import {
  Plus, Trash2, Pencil, X, Check, RefreshCw, BarChart3,
  TrendingUp, TrendingDown, Wallet, Brain, ChevronDown, ChevronUp,
  Shield, Zap, AlertTriangle,
} from "lucide-react";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"];
const RANGES = [
  { value: "1mo", label: "1M" }, { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" }, { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" }, { value: "5y", label: "5Y" },
];

// Mini sparkline component
function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const h = 32;
  const w = 80;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`).join(" ");
  return (
    <svg width={w} height={h} className="shrink-0">
      <polyline fill="none" stroke={positive ? "#10b981" : "#ef4444"} strokeWidth="1.5" points={points} />
    </svg>
  );
}

// P&L badge
function PnlBadge({ value, pct, size = "md" }: { value: number; pct?: number; size?: "sm" | "md" }) {
  const positive = value >= 0;
  const cls = size === "sm" ? "text-[11px] px-1.5 py-0.5" : "text-xs px-2 py-1";
  return (
    <span className={`${cls} rounded-md font-medium inline-flex items-center gap-1 ${positive ? "bg-green-500/15 text-green-500" : "bg-red-500/15 text-red-500"}`}>
      {positive ? "+" : ""}{formatCurrency(value)}
      {pct !== undefined && <span className="opacity-75">({positive ? "+" : ""}{pct.toFixed(1)}%)</span>}
    </span>
  );
}

function AnalysisCard({ title, analysis, olderList, showOlder, onLoadOlder, onCloseOlder, onViewOlder }: {
  title: string;
  analysis: PortfolioAnalysis | null;
  olderList: AnalysisListItem[];
  showOlder: boolean;
  onLoadOlder: () => void;
  onCloseOlder: () => void;
  onViewOlder: (id: string) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-1.5"><Brain className="h-4 w-4" />{title}</CardTitle>
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onLoadOlder}>View older</Button>
        </div>
      </CardHeader>
      <CardContent>
        {showOlder && (
          <div className="mb-4 space-y-1.5 p-3 rounded-lg bg-accent/20">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium">Previous Reports</span>
              <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={onCloseOlder}><X className="h-3 w-3" /></Button>
            </div>
            {olderList.length === 0 ? (
              <p className="text-xs text-muted-foreground">No older reports.</p>
            ) : olderList.map((a) => (
              <div key={a.id} className={`flex items-center justify-between p-2 rounded cursor-pointer transition-colors text-xs ${analysis?.id === a.id ? "bg-accent" : "hover:bg-accent/50"}`}
                onClick={() => onViewOlder(a.id)}>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${a.market_sentiment === "bullish" ? "bg-green-500" : a.market_sentiment === "bearish" ? "bg-red-500" : "bg-yellow-500"}`} />
                  <span className="capitalize">{a.market_sentiment || "neutral"}</span>
                </div>
                <span className="text-muted-foreground">{new Date(a.created_at).toLocaleDateString("en-CH", { day: "numeric", month: "short", year: "numeric" })}</span>
              </div>
            ))}
          </div>
        )}

        {!analysis ? (
          <p className="text-sm text-muted-foreground py-4">No analysis yet. Your agent will store reports here.</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                analysis.content.market_sentiment === "bullish" ? "bg-green-500/15 text-green-500" :
                analysis.content.market_sentiment === "bearish" ? "bg-red-500/15 text-red-500" :
                "bg-yellow-500/15 text-yellow-500"
              }`}>{analysis.content.market_sentiment}</span>
              <span className="text-xs text-muted-foreground">{new Date(analysis.created_at).toLocaleString()}</span>
            </div>

            <div className="p-3 rounded-lg bg-accent/30">
              <p className="text-sm">{analysis.content.market_summary}</p>
            </div>

            {/* Portfolio stocks */}
            {analysis.content.stocks && analysis.content.stocks.length > 0 && (
              <div className="space-y-3">
                {analysis.content.stocks.map((s) => (
                  <div key={s.symbol} className="p-4 rounded-lg border">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold">{s.symbol}</span>
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          s.action === "ADD" ? "bg-green-500/15 text-green-500" :
                          s.action === "SELL" ? "bg-red-500/15 text-red-500" :
                          "bg-blue-500/15 text-blue-500"
                        }`}>{s.action}</span>
                      </div>
                      <div className="text-right text-xs">
                        <span className="text-muted-foreground">Entry: {s.entry_price.toFixed(2)}</span>
                        <span className="mx-1.5 text-muted-foreground">/</span>
                        <span>Now: {s.current_price.toFixed(2)}</span>
                        <span className={`ml-2 ${s.unrealized_pnl_pct >= 0 ? "text-green-500" : "text-red-500"}`}>
                          {s.unrealized_pnl_pct >= 0 ? "+" : ""}{s.unrealized_pnl_pct.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground mb-2">{s.rationale}</p>
                    <div className="flex gap-4 text-xs">
                      {s.key_risks.length > 0 && (
                        <div className="flex-1">
                          <p className="font-medium text-red-400 flex items-center gap-1 mb-1"><AlertTriangle className="h-3 w-3" />Risks</p>
                          <ul className="space-y-0.5 text-muted-foreground">{s.key_risks.map((r, i) => <li key={i}>- {r}</li>)}</ul>
                        </div>
                      )}
                      {s.key_catalysts.length > 0 && (
                        <div className="flex-1">
                          <p className="font-medium text-green-400 flex items-center gap-1 mb-1"><Zap className="h-3 w-3" />Catalysts</p>
                          <ul className="space-y-0.5 text-muted-foreground">{s.key_catalysts.map((c, i) => <li key={i}>- {c}</li>)}</ul>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Economy indicators */}
            {analysis.content.key_indicators && analysis.content.key_indicators.length > 0 && (
              <div className="grid gap-2 grid-cols-2 md:grid-cols-4">
                {analysis.content.key_indicators.map((ind, i) => (
                  <div key={i} className="p-3 rounded-lg border text-center">
                    <p className="text-[11px] text-muted-foreground">{ind.name}</p>
                    <p className="text-lg font-bold">{ind.value}</p>
                    <p className={`text-[10px] ${ind.trend === "up" ? "text-green-500" : ind.trend === "down" ? "text-red-500" : "text-muted-foreground"}`}>
                      {ind.trend === "up" ? "Trending up" : ind.trend === "down" ? "Trending down" : "Stable"}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {analysis.content.outlook && (
              <div className="p-3 rounded-lg border">
                <p className="text-xs font-medium mb-1">Outlook</p>
                <p className="text-sm text-muted-foreground">{analysis.content.outlook}</p>
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              {analysis.content.risks && analysis.content.risks.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-red-400 flex items-center gap-1 mb-2"><AlertTriangle className="h-3 w-3" />Key Risks</p>
                  <ul className="space-y-1 text-xs text-muted-foreground">{analysis.content.risks.map((r, i) => <li key={i} className="flex gap-1.5"><span className="text-red-400">-</span>{r}</li>)}</ul>
                </div>
              )}
              {analysis.content.opportunities && analysis.content.opportunities.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-green-400 flex items-center gap-1 mb-2"><Zap className="h-3 w-3" />Opportunities</p>
                  <ul className="space-y-1 text-xs text-muted-foreground">{analysis.content.opportunities.map((o, i) => <li key={i} className="flex gap-1.5"><span className="text-green-400">-</span>{o}</li>)}</ul>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

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
  const [historyData, setHistoryData] = useState<{ date: string; value: number }[]>([]);
  const [historyRange, setHistoryRange] = useState("3mo");
  const [latestPortfolio, setLatestPortfolio] = useState<PortfolioAnalysis | null>(null);
  const [latestEconomy, setLatestEconomy] = useState<PortfolioAnalysis | null>(null);
  const [activePortfolio, setActivePortfolio] = useState<PortfolioAnalysis | null>(null);
  const [activeEconomy, setActiveEconomy] = useState<PortfolioAnalysis | null>(null);
  const [olderPortfolio, setOlderPortfolio] = useState<AnalysisListItem[]>([]);
  const [olderEconomy, setOlderEconomy] = useState<AnalysisListItem[]>([]);
  const [showOlderPortfolio, setShowOlderPortfolio] = useState(false);
  const [showOlderEconomy, setShowOlderEconomy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.portfolio(),
      api.portfolioHistory(historyRange === "1mo" ? 30 : historyRange === "3mo" ? 90 : historyRange === "1y" ? 365 : 180),
      api.analysisLatest("portfolio"),
      api.analysisLatest("economy"),
    ]).then(([p, h, ap, ae]) => {
      setPortfolio(p);
      setHistoryData(h);
      if (ap && !("status" in ap && ap.status === "none")) { setLatestPortfolio(ap); setActivePortfolio(ap); }
      if (ae && !("status" in ae && ae.status === "none")) { setLatestEconomy(ae); setActiveEconomy(ae); }
    }).finally(() => setLoading(false));
  }, [historyRange]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { const i = setInterval(load, 120000); return () => clearInterval(i); }, [load]);

  // Auto-select first stock on initial load
  useEffect(() => {
    if (!chartTicker && portfolio?.positions.length) {
      openChart(portfolio.positions[0].symbol);
    }
  }, [portfolio?.positions.length]); // eslint-disable-line

  const handleTrade = async () => {
    const f = tradeForm;
    if (!f.quantity || (f.type !== "deposit" && f.type !== "withdraw" && !f.symbol)) return;
    setTrading(true); setTradeError("");
    try {
      await api.trade({
        symbol: f.type === "deposit" || f.type === "withdraw" ? "CASH" : f.symbol.toUpperCase().trim(),
        type: f.type, quantity: parseFloat(f.quantity),
        price: f.price ? parseFloat(f.price) : undefined,
        currency: f.currency, date: f.date || undefined,
        fees: f.fees ? parseFloat(f.fees) : 0, deduct_from_cash: f.deduct_from_cash,
      });
      setTradeForm({ symbol: "", type: "buy", quantity: "", price: "", currency: "USD", date: new Date().toISOString().split("T")[0], fees: "", deduct_from_cash: true });
      setShowTrade(false); load();
    } catch (e) { setTradeError(e instanceof Error ? e.message : "Trade failed"); }
    finally { setTrading(false); }
  };

  const handleUpdate = async (id: string) => {
    await api.updatePosition(id, {
      quantity: editForm.quantity ? parseFloat(editForm.quantity) : undefined,
      avg_cost_price: editForm.avg_cost_price ? parseFloat(editForm.avg_cost_price) : undefined,
    });
    setEditingId(null); load();
  };

  const handleDelete = async (id: string) => { await api.deletePosition(id); load(); };

  const viewAnalysis = async (id: string, type: "portfolio" | "economy") => {
    try {
      const a = await api.analysisDetail(id);
      if (type === "portfolio") { setActivePortfolio(a); setShowOlderPortfolio(false); }
      else { setActiveEconomy(a); setShowOlderEconomy(false); }
    } catch { /* ignore */ }
  };

  const loadOlderPortfolio = async () => {
    const list = await api.analysisList("portfolio", 20);
    setOlderPortfolio(list);
    setShowOlderPortfolio(true);
  };

  const loadOlderEconomy = async () => {
    const list = await api.analysisList("economy", 20);
    setOlderEconomy(list);
    setShowOlderEconomy(true);
  };

  const openChart = async (ticker: string, range = chartRange) => {
    setChartTicker(ticker); setChartRange(range); setChartLoading(true);
    try { const res = await api.priceChart(ticker, range); setChartData(res.data); }
    catch { setChartData([]); }
    finally { setChartLoading(false); }
  };

  useEffect(() => { if (chartTicker) openChart(chartTicker, chartRange); }, [chartRange]); // eslint-disable-line

  if (loading && !portfolio) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-64" />
        <Skeleton className="h-64" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const p = portfolio;
  const pnlPositive = (p?.total_pnl ?? 0) >= 0;

  return (
    <div className="space-y-6">
      {/* Hero Section — Portfolio Value + P&L */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">Portfolio Value</p>
          <p className="text-4xl font-bold tracking-tight">{formatCurrency(p?.total_value ?? 0)}</p>
          <div className="flex items-center gap-3 mt-2">
            <PnlBadge value={p?.total_pnl ?? 0} pct={p?.total_pnl_pct ?? 0} />
            <span className="text-sm text-muted-foreground">All time</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />Refresh
          </Button>
          <Button size="sm" onClick={() => setShowTrade(true)}>
            <Plus className="h-4 w-4 mr-1" />Trade
          </Button>
        </div>
      </div>

      {/* Portfolio History Chart */}
      {historyData.length > 1 && (
        <Card className="border-0 bg-transparent shadow-none">
          <CardContent className="p-0">
            <div className="flex gap-1 mb-3">
              {[{ value: "1mo", label: "1M" }, { value: "3mo", label: "3M" }, { value: "1y", label: "1Y" }].map((r) => (
                <Button key={r.value} variant={historyRange === r.value ? "default" : "ghost"} size="sm" className="h-7 text-xs px-3"
                  onClick={() => setHistoryRange(r.value)}>{r.label}</Button>
              ))}
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={historyData}>
                  <defs>
                    <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={pnlPositive ? "#10b981" : "#ef4444"} stopOpacity={0.2} />
                      <stop offset="100%" stopColor={pnlPositive ? "#10b981" : "#ef4444"} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} stroke="#555" />
                  <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} stroke="#555" tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Area type="monotone" dataKey="value" stroke={pnlPositive ? "#10b981" : "#ef4444"} strokeWidth={2} fill="url(#portfolioGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary Cards */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Invested</p>
            <p className="text-lg font-bold">{formatCurrency(p?.total_cost ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Cash</p>
            <p className="text-lg font-bold">{formatCurrency(p?.cash_balance ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Positions</p>
            <p className="text-lg font-bold">{p?.positions_count ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Total (incl. cash)</p>
            <p className="text-lg font-bold">{formatCurrency((p?.total_value ?? 0) + (p?.cash_balance ?? 0))}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        {/* Allocation Donut — compact */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-1 px-4 pt-3"><CardTitle className="text-xs">Allocation</CardTitle></CardHeader>
          <CardContent className="h-48 px-2">
            {(p?.positions.length ?? 0) === 0 ? (
              <p className="text-xs text-muted-foreground pt-6 text-center">No positions</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={p!.positions} dataKey="market_value" nameKey="symbol" cx="50%" cy="50%"
                    outerRadius={65} innerRadius={40}
                    label={((e: { symbol: string; weight_pct: number }) => `${e.symbol} ${e.weight_pct.toFixed(0)}%`) as unknown as boolean}>
                    {p!.positions.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Holdings List */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-1 px-4 pt-3"><CardTitle className="text-xs">Holdings</CardTitle></CardHeader>
          <CardContent className="px-2">
            {(p?.positions.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground p-2">Click "Trade" to add your first position.</p>
            ) : (
              <div className="space-y-0.5 max-h-[400px] overflow-y-auto">
                {p!.positions.map((pos) => (
                  editingId === pos.id ? (
                    <div key={pos.id} className="flex items-center gap-2 p-3 rounded-lg bg-primary/5">
                      <span className="font-bold text-sm w-16">{pos.symbol}</span>
                      <Input value={editForm.quantity} onChange={(e) => setEditForm({ ...editForm, quantity: e.target.value })} className="h-8 w-20 text-sm" placeholder="Qty" />
                      <Input value={editForm.avg_cost_price} onChange={(e) => setEditForm({ ...editForm, avg_cost_price: e.target.value })} className="h-8 w-24 text-sm" placeholder="Avg price" />
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => handleUpdate(pos.id)}><Check className="h-3.5 w-3.5 text-green-500" /></Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditingId(null)}><X className="h-3.5 w-3.5" /></Button>
                    </div>
                  ) : (
                    <div key={pos.id} className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors group ${chartTicker === pos.symbol ? "bg-accent" : "hover:bg-accent/40"}`}
                      onClick={() => openChart(pos.symbol)}>
                      {/* Left: ticker + name */}
                      <div className="min-w-[100px]">
                        <p className="font-bold text-sm">{pos.symbol}</p>
                        <p className="text-[11px] text-muted-foreground truncate max-w-[120px]">{pos.name}</p>
                      </div>

                      {/* Sparkline */}
                      <Sparkline data={pos.sparkline} positive={pos.change >= 0} />

                      {/* Price + day change */}
                      <div className="text-right min-w-[90px]">
                        <p className="text-sm font-medium">{pos.last_price?.toFixed(2)}</p>
                        <p className={`text-[11px] ${pos.change >= 0 ? "text-green-500" : "text-red-500"}`}>
                          {pos.change >= 0 ? "+" : ""}{pos.change.toFixed(2)} ({pos.change_pct >= 0 ? "+" : ""}{pos.change_pct.toFixed(1)}%)
                        </p>
                      </div>

                      {/* Shares + value */}
                      <div className="text-right min-w-[80px] hidden md:block">
                        <p className="text-sm font-medium">{formatCurrency(pos.market_value)}</p>
                        <p className="text-[11px] text-muted-foreground">{pos.quantity} shares</p>
                      </div>

                      {/* P&L badge */}
                      <div className="min-w-[100px] text-right hidden sm:block">
                        <PnlBadge value={pos.unrealized_pnl} pct={pos.pnl_pct} size="sm" />
                      </div>

                      {/* Actions */}
                      <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditingId(pos.id); setEditForm({ quantity: String(pos.quantity), avg_cost_price: String(pos.avg_cost_price) }); }}>
                          <Pencil className="h-3 w-3 text-muted-foreground" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => handleDelete(pos.id)}>
                          <Trash2 className="h-3 w-3 text-muted-foreground" />
                        </Button>
                      </div>
                    </div>
                  )
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Inline Chart Panel */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-1 px-4 pt-3">
            <CardTitle className="text-xs flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5" />
              {chartTicker || "Select a stock"}
              {chartTicker && (() => {
                const pos = p?.positions.find((pp) => pp.symbol === chartTicker);
                return pos ? <span className="font-normal text-muted-foreground ml-1">{pos.name}</span> : null;
              })()}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-3">
            {!chartTicker ? (
              <div className="h-64 flex items-center justify-center text-sm text-muted-foreground">Click a holding to view its chart</div>
            ) : (
              <>
                {(() => {
                  const pos = p?.positions.find((pp) => pp.symbol === chartTicker);
                  return pos ? (
                    <div className="flex items-center gap-3 mb-3 flex-wrap">
                      <span className="text-lg font-bold">{pos.last_price?.toFixed(2)}</span>
                      <span className={`text-xs ${pos.change >= 0 ? "text-green-500" : "text-red-500"}`}>
                        {pos.change >= 0 ? "+" : ""}{pos.change.toFixed(2)} ({pos.change_pct >= 0 ? "+" : ""}{pos.change_pct.toFixed(1)}%)
                      </span>
                      <span className="text-xs text-muted-foreground">{pos.quantity} shares</span>
                      <PnlBadge value={pos.unrealized_pnl} pct={pos.pnl_pct} size="sm" />
                    </div>
                  ) : null;
                })()}
                <div className="flex gap-1 mb-2">
                  {RANGES.map((r) => (
                    <Button key={r.value} variant={chartRange === r.value ? "default" : "ghost"} size="sm" className="h-6 text-[10px] px-2" onClick={() => setChartRange(r.value)}>{r.label}</Button>
                  ))}
                </div>
                <div className="h-56">
                  {chartLoading ? (
                    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">Loading...</div>
                  ) : chartData.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No data.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData}>
                        <defs>
                          <linearGradient id="stockGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => d.slice(5)} stroke="#555" />
                        <YAxis tick={{ fontSize: 9 }} domain={["auto", "auto"]} stroke="#555" />
                        <Tooltip formatter={(v) => Number(v).toFixed(2)} />
                        <Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#stockGrad)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Portfolio Analysis */}
      <AnalysisCard
        title="Portfolio Analysis"
        analysis={activePortfolio}
        olderList={olderPortfolio}
        showOlder={showOlderPortfolio}
        onLoadOlder={loadOlderPortfolio}
        onCloseOlder={() => setShowOlderPortfolio(false)}
        onViewOlder={(id) => viewAnalysis(id, "portfolio")}
      />

      {/* Economy Analysis */}
      <AnalysisCard
        title="Economy & Market"
        analysis={activeEconomy}
        olderList={olderEconomy}
        showOlder={showOlderEconomy}
        onLoadOlder={loadOlderEconomy}
        onCloseOlder={() => setShowOlderEconomy(false)}
        onViewOlder={(id) => viewAnalysis(id, "economy")}
      />

      {/* Trade Dialog */}
      <Dialog open={showTrade} onOpenChange={setShowTrade}>
        <DialogContent>
          <DialogHeader><DialogTitle>Record Trade</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-4 gap-1">
              {(["buy", "sell", "deposit", "withdraw"] as const).map((t) => (
                <Button key={t} variant={tradeForm.type === t ? "default" : "outline"} size="sm" onClick={() => setTradeForm({ ...tradeForm, type: t })} className="capitalize">{t}</Button>
              ))}
            </div>
            {tradeForm.type !== "deposit" && tradeForm.type !== "withdraw" && (
              <div>
                <label className="text-xs text-muted-foreground">Ticker</label>
                <Input placeholder="AAPL, NVDA, BTC-USD..." value={tradeForm.symbol} onChange={(e) => setTradeForm({ ...tradeForm, symbol: e.target.value })} />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">{tradeForm.type === "deposit" || tradeForm.type === "withdraw" ? "Amount" : "Quantity"}</label>
                <Input type="number" value={tradeForm.quantity} onChange={(e) => setTradeForm({ ...tradeForm, quantity: e.target.value })} />
              </div>
              {tradeForm.type !== "deposit" && tradeForm.type !== "withdraw" && (
                <div>
                  <label className="text-xs text-muted-foreground">Price (empty = market)</label>
                  <Input type="number" value={tradeForm.price} onChange={(e) => setTradeForm({ ...tradeForm, price: e.target.value })} />
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
                  {["USD", "CHF", "EUR", "GBP", "KRW"].map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            {(tradeForm.type === "buy" || tradeForm.type === "sell") && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={tradeForm.deduct_from_cash} onChange={(e) => setTradeForm({ ...tradeForm, deduct_from_cash: e.target.checked })} />
                {tradeForm.type === "buy" ? "Deduct from cash" : "Add proceeds to cash"}
              </label>
            )}
            {tradeError && <p className="text-xs text-red-500">{tradeError}</p>}
            <Button onClick={handleTrade} disabled={trading} className="w-full capitalize">{trading ? "Processing..." : tradeForm.type}</Button>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
}
