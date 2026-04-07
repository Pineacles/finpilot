"use client";

import { useEffect, useState } from "react";
import { api, PortfolioSummary, PortfolioSnapshot, AnalysisResult } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import {
  Brain,
  TrendingUp,
  Globe,
  BarChart3,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Info,
} from "lucide-react";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"];

const ANALYSIS_TYPES = [
  { type: "position", label: "Position", icon: TrendingUp },
  { type: "macro", label: "Macro", icon: Globe },
  { type: "sector", label: "Sector", icon: BarChart3 },
];

const RISK_COLORS: Record<string, string> = {
  low: "bg-green-500/10 text-green-500",
  medium: "bg-yellow-500/10 text-yellow-500",
  high: "bg-red-500/10 text-red-500",
};

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);

  const loadAnalyses = () => {
    api.analysisLatest().then(setAnalyses);
  };

  useEffect(() => {
    Promise.all([api.portfolio(), api.portfolioHistory(), api.analysisLatest()])
      .then(([p, h, a]) => { setPortfolio(p); setHistory(h); setAnalyses(a); })
      .finally(() => setLoading(false));
  }, []);

  const runAnalysis = async (type: string) => {
    setRunning(type);
    try {
      await api.runAnalysis(type);
      loadAnalyses();
    } finally {
      setRunning(null);
    }
  };

  const getAnalysis = (type: string) => analyses.find((a) => a.analysis_type === type);

  if (loading) {
    return <div className="space-y-6"><h1 className="text-3xl font-bold">Portfolio</h1><Skeleton className="h-96" /></div>;
  }
  if (!portfolio) return <p>Failed to load portfolio</p>;

  const pieData = portfolio.positions.map((p) => ({
    name: p.symbol,
    value: p.market_value || 0,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Portfolio</h1>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Total Value</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-bold">{formatCurrency(portfolio.total_value)}</p></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Total P&L</CardTitle></CardHeader>
          <CardContent>
            <p className={`text-2xl font-bold ${portfolio.total_pnl >= 0 ? "text-green-500" : "text-red-500"}`}>
              {formatCurrency(portfolio.total_pnl)} ({formatPct(portfolio.total_pnl_pct)})
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Positions</CardTitle></CardHeader>
          <CardContent><p className="text-2xl font-bold">{portfolio.positions_count}</p></CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Allocation</CardTitle></CardHeader>
          <CardContent className="h-72">
            {pieData.length === 0 ? (
              <p className="text-sm text-muted-foreground">No positions yet. Sync from Saxo Bank.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}>
                    {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Performance (90 days)</CardTitle></CardHeader>
          <CardContent className="h-72">
            {history.length === 0 ? (
              <p className="text-sm text-muted-foreground">No history yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="snapshot_date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Line type="monotone" dataKey="total_value" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Positions Table */}
      <Card>
        <CardHeader><CardTitle>Positions</CardTitle></CardHeader>
        <CardContent>
          {portfolio.positions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No positions. Connect Saxo Bank in Settings.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Avg Cost</TableHead>
                  <TableHead className="text-right">Last Price</TableHead>
                  <TableHead className="text-right">Market Value</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                  <TableHead className="text-right">Weight</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {portfolio.positions.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.symbol}</TableCell>
                    <TableCell className="text-muted-foreground">{p.name}</TableCell>
                    <TableCell className="text-right">{p.quantity}</TableCell>
                    <TableCell className="text-right">{formatCurrency(p.avg_cost_price, p.currency)}</TableCell>
                    <TableCell className="text-right">{p.last_price ? formatCurrency(p.last_price, p.currency) : "—"}</TableCell>
                    <TableCell className="text-right">{formatCurrency(p.market_value || 0, p.currency)}</TableCell>
                    <TableCell className={`text-right ${(p.unrealized_pnl || 0) >= 0 ? "text-green-500" : "text-red-500"}`}>
                      {formatCurrency(p.unrealized_pnl || 0, p.currency)}
                    </TableCell>
                    <TableCell className="text-right">{(p.weight_pct || 0).toFixed(1)}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* AI Analysis */}
      <div className="flex items-center gap-2 pt-2">
        <Brain className="h-5 w-5 text-primary" />
        <h2 className="text-xl font-bold">AI Analysis</h2>
      </div>

      <Tabs defaultValue="position">
        <TabsList>
          {ANALYSIS_TYPES.map(({ type, label, icon: Icon }) => (
            <TabsTrigger key={type} value={type}>
              <Icon className="h-4 w-4 mr-1" />{label}
            </TabsTrigger>
          ))}
        </TabsList>

        {ANALYSIS_TYPES.map(({ type, label }) => {
          const analysis = getAnalysis(type);
          const content = analysis?.content;

          return (
            <TabsContent key={type} value={type} className="space-y-4 mt-4">
              <div className="flex justify-between items-center">
                <div>
                  {analysis && (
                    <p className="text-xs text-muted-foreground">
                      Last run: {new Date(analysis.created_at).toLocaleString()} · {analysis.model_used}
                    </p>
                  )}
                </div>
                <Button onClick={() => runAnalysis(type)} disabled={running === type} variant="outline" size="sm">
                  <RefreshCw className={`h-4 w-4 mr-2 ${running === type ? "animate-spin" : ""}`} />
                  {running === type ? "Analyzing..." : `Run ${label}`}
                </Button>
              </div>

              {!analysis ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <Brain className="h-10 w-10 mx-auto mb-3 text-muted-foreground" />
                    <p className="text-muted-foreground">No {label.toLowerCase()} analysis yet.</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Set up an Anthropic API key or custom agent endpoint in Settings, then click Run.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {/* Summary + Risk */}
                  <div className="grid gap-4 md:grid-cols-3">
                    <Card className="md:col-span-2">
                      <CardHeader className="pb-2"><CardTitle className="text-sm">Summary</CardTitle></CardHeader>
                      <CardContent><p className="text-sm">{content?.summary || "No summary."}</p></CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="pb-2"><CardTitle className="text-sm">Risk</CardTitle></CardHeader>
                      <CardContent className="flex items-center gap-3">
                        {content?.risk_level === "high" && <AlertTriangle className="h-6 w-6 text-red-500" />}
                        {content?.risk_level === "medium" && <Info className="h-6 w-6 text-yellow-500" />}
                        {content?.risk_level === "low" && <CheckCircle2 className="h-6 w-6 text-green-500" />}
                        <Badge className={RISK_COLORS[content?.risk_level || "medium"] || ""}>
                          {content?.risk_level?.toUpperCase() || "UNKNOWN"}
                        </Badge>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Insights + Recommendations side by side */}
                  <div className="grid gap-4 md:grid-cols-2">
                    {content?.key_insights && content.key_insights.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2"><CardTitle className="text-sm">Key Insights</CardTitle></CardHeader>
                        <CardContent>
                          <ul className="space-y-1.5">
                            {content.key_insights.map((insight, i) => (
                              <li key={i} className="flex gap-2 text-sm"><span className="text-primary">•</span>{insight}</li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                    )}
                    {content?.recommendations && content.recommendations.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2"><CardTitle className="text-sm">Recommendations</CardTitle></CardHeader>
                        <CardContent>
                          <ul className="space-y-1.5">
                            {content.recommendations.map((rec, i) => (
                              <li key={i} className="flex gap-2 text-sm"><span className="text-green-500">→</span>{rec}</li>
                            ))}
                          </ul>
                        </CardContent>
                      </Card>
                    )}
                  </div>

                  {/* Position Notes */}
                  {content?.position_notes && Object.keys(content.position_notes).length > 0 && (
                    <Card>
                      <CardHeader className="pb-2"><CardTitle className="text-sm">Position Notes</CardTitle></CardHeader>
                      <CardContent className="space-y-2">
                        {Object.entries(content.position_notes).map(([symbol, note]) => (
                          <div key={symbol} className="flex gap-3 items-start">
                            <Badge variant="secondary" className="font-mono shrink-0">{symbol}</Badge>
                            <p className="text-sm">{note}</p>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}

                  {/* Macro Outlook */}
                  {content?.macro_outlook && (
                    <Card>
                      <CardHeader className="pb-2"><CardTitle className="text-sm">Macro Outlook</CardTitle></CardHeader>
                      <CardContent><p className="text-sm">{content.macro_outlook}</p></CardContent>
                    </Card>
                  )}
                </div>
              )}
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
