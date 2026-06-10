"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine,
  type TooltipProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { TrendingUp, TrendingDown, Info, Settings2, LineChart as LineChartIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { GlassCard } from "@/components/glass-card";
import {
  api,
  type AssetType,
  type BenchmarkComparison,
  type BenchmarkCountedSymbol,
  type BenchmarkExcludedSymbol,
} from "@/lib/api";

type RangeKey = "1W" | "1M" | "3M" | "YTD" | "1Y" | "ALL" | "CUSTOM";

const RANGES: { value: RangeKey; label: string }[] = [
  { value: "1W", label: "1W" },
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "YTD", label: "YTD" },
  { value: "1Y", label: "1Y" },
  { value: "ALL", label: "All" },
  { value: "CUSTOM", label: "Custom" },
];

const ASSET_TYPES: AssetType[] = ["equity", "etf", "index", "crypto", "bond", "commodity", "cash"];

const ASSET_TYPE_COLORS: Record<AssetType, string> = {
  equity: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  etf: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400",
  index: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400",
  crypto: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  bond: "bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-400",
  commodity: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400",
  cash: "bg-muted text-muted-foreground",
};

const SOURCE_LABEL: Record<string, string> = {
  auto: "auto",
  user: "you",
  agent: "agent",
};

function AssetTypePill({ type, source }: { type: AssetType; source: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-lg font-medium ${ASSET_TYPE_COLORS[type] || ASSET_TYPE_COLORS.equity}`}>
      {type}
      <span className="opacity-60">· {SOURCE_LABEL[source] || source}</span>
    </span>
  );
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function CustomTooltip({ active, payload, label }: TooltipProps<ValueType, NameType>) {
  if (!active || !payload || payload.length === 0) return null;

  const portEntry = payload.find((p) => p.dataKey === "portfolio");
  const benchEntry = payload.find((p) => p.dataKey === "benchmark");

  const portVal = portEntry?.value ?? null;
  const benchVal = benchEntry?.value ?? null;
  const contributors: Record<string, number> = portEntry?.payload?.contributors ?? {};
  const alphaVal = portVal !== null && benchVal !== null ? portVal - benchVal : null;

  return (
    <div className="rounded-xl border border-border/60 bg-background/95 shadow-lg p-3 text-[12px] min-w-[160px]">
      <div className="font-medium text-foreground mb-2">{label ? fmtDate(label) : ""}</div>
      {portVal !== null && (
        <div className="mb-1">
          <span className="text-blue-500 font-medium">Portfolio</span>
          <span className="ml-2 tabular-nums font-semibold">{portVal >= 100 ? "+" : ""}{(portVal - 100).toFixed(2)}%</span>
        </div>
      )}
      {Object.entries(contributors).length > 0 && (
        <div className="pl-2 border-l border-blue-500/30 mb-2 space-y-0.5">
          {Object.entries(contributors)
            .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
            .slice(0, 5)
            .map(([sym, pp]) => (
              <div key={sym} className="flex justify-between gap-3 text-[11px] text-muted-foreground">
                <span className="font-mono">{sym}</span>
                <span className={`tabular-nums ${pp >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                  {pp >= 0 ? "+" : ""}{pp.toFixed(2)}pp
                </span>
              </div>
            ))}
        </div>
      )}
      {benchVal !== null && (
        <div className="mb-1">
          <span className="text-orange-500 font-medium">S&amp;P 500</span>
          <span className="ml-2 tabular-nums font-semibold">{benchVal >= 100 ? "+" : ""}{(benchVal - 100).toFixed(2)}%</span>
        </div>
      )}
      {alphaVal !== null && (
        <div className={`text-[11px] font-medium ${alphaVal >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
          Alpha: {alphaVal >= 0 ? "+" : ""}{alphaVal.toFixed(2)}pp
        </div>
      )}
    </div>
  );
}

function MergedChart({ data }: { data: { date: string; portfolio: number | null; benchmark: number | null; contributors?: Record<string, number> }[] }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 12, right: 20, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
        <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} tickFormatter={(v) => `${v.toFixed(0)}`} />
        <ReferenceLine y={100} stroke="currentColor" strokeOpacity={0.2} strokeDasharray="4 4" />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="portfolio" name="Your stocks" stroke="#3b82f6" strokeWidth={2.5} dot={false} connectNulls={false} />
        <Line type="monotone" dataKey="benchmark" name="S&P 500" stroke="#f97316" strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function BenchmarkCard() {
  const [range, setRange] = useState<RangeKey>("1M");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [data, setData] = useState<BenchmarkComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [classifyOpen, setClassifyOpen] = useState<{ symbol: string; currentType: AssetType } | null>(null);

  const load = useCallback(async () => {
    if (range === "CUSTOM" && (!customStart || !customEnd)) return;
    setLoading(true); setError(null);
    try {
      const r = await api.benchmarkComparison({
        range,
        benchmark: "SPY",
        start: range === "CUSTOM" ? customStart : undefined,
        end: range === "CUSTOM" ? customEnd : undefined,
      });
      setData(r);
    } catch (e: any) {
      setError(e?.message || "Failed to load benchmark comparison");
    } finally {
      setLoading(false);
    }
  }, [range, customStart, customEnd]);

  useEffect(() => { load(); }, [load]);

  const chartData = useMemo(() => {
    if (!data) return [];
    const byDate = new Map<string, { date: string; portfolio: number | null; benchmark: number | null; contributors?: Record<string, number> }>();
    for (const p of data.portfolio_series) {
      byDate.set(p.date, { date: p.date, portfolio: p.index, benchmark: null, contributors: p.contributors });
    }
    for (const b of data.benchmark_series) {
      const ex = byDate.get(b.date);
      if (ex) ex.benchmark = b.index;
      else byDate.set(b.date, { date: b.date, portfolio: null, benchmark: b.index });
    }
    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [data]);

  const handleReclassify = async (assetType: AssetType) => {
    if (!classifyOpen) return;
    try {
      await api.setClassification(classifyOpen.symbol, assetType);
      setClassifyOpen(null);
      await load();
    } catch (e: any) {
      alert(e?.message || "Classification failed");
    }
  };

  const summary = data?.summary;
  const outperformed = summary ? summary.alpha_pct > 0 : false;

  return (
    <>
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-2xl bg-blue-100 dark:bg-blue-500/15 flex items-center justify-center">
          <LineChartIcon className="h-5 w-5 text-blue-600 dark:text-blue-400" strokeWidth={1.8} />
        </div>
        <h2 className="text-[16px] font-semibold">Benchmark vs. S&amp;P 500</h2>
        <span className="text-[12px] px-2 py-0.5 rounded-full bg-accent text-muted-foreground font-medium">
          {data ? data.counted_symbols.length : 0} stocks
        </span>
        <Button variant="outline" size="sm" onClick={() => setDetailsOpen(true)} className="ml-auto gap-1.5">
          <Settings2 className="h-3.5 w-3.5" />
          Details
        </Button>
      </div>
      <GlassCard className="space-y-4" delay={0.04}>

        <div className="flex items-center gap-2 flex-wrap">
          {RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => setRange(r.value)}
              className={`px-3 py-1 rounded-xl text-[12px] font-medium transition ${
                range === r.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/60 text-foreground/70 hover:bg-muted"
              }`}
            >
              {r.label}
            </button>
          ))}
          {range === "CUSTOM" && (
            <div className="flex items-center gap-1.5">
              <Input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} className="h-8 text-[12px] w-[140px]" />
              <span className="text-[12px] text-muted-foreground">→</span>
              <Input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} className="h-8 text-[12px] w-[140px]" />
            </div>
          )}
        </div>

        {loading && <div className="text-center text-[13px] text-muted-foreground py-10">Computing…</div>}
        {error && <div className="text-center text-[13px] text-loss py-10">{error}</div>}

        {!loading && !error && data && data.portfolio_series.length === 0 && (
          <div className="text-center text-[13px] text-muted-foreground py-10">
            {data.caveats[0] || "No data in this range."}
          </div>
        )}

        {!loading && !error && data && data.portfolio_series.length > 0 && summary && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-2xl bg-muted/40 p-3">
                <div className="text-[11px] text-muted-foreground">You</div>
                <div className={`text-[20px] font-bold tabular-nums ${summary.portfolio_return_pct >= 0 ? "text-gain" : "text-loss"}`}>
                  {summary.portfolio_return_pct >= 0 ? "+" : ""}{summary.portfolio_return_pct.toFixed(2)}%
                </div>
              </div>
              <div className="rounded-2xl bg-muted/40 p-3">
                <div className="text-[11px] text-muted-foreground">S&amp;P 500</div>
                <div className={`text-[20px] font-bold tabular-nums ${summary.benchmark_return_pct >= 0 ? "text-gain" : "text-loss"}`}>
                  {summary.benchmark_return_pct >= 0 ? "+" : ""}{summary.benchmark_return_pct.toFixed(2)}%
                </div>
              </div>
              <div className={`rounded-2xl p-3 ${outperformed ? "bg-emerald-500/10" : "bg-rose-500/10"}`}>
                <div className="text-[11px] text-muted-foreground flex items-center gap-1">
                  Alpha {outperformed ? <TrendingUp className="h-3 w-3 text-gain" /> : <TrendingDown className="h-3 w-3 text-loss" />}
                </div>
                <div className={`text-[20px] font-bold tabular-nums ${outperformed ? "text-gain" : "text-loss"}`}>
                  {summary.alpha_pct >= 0 ? "+" : ""}{summary.alpha_pct.toFixed(2)}pp
                </div>
              </div>
            </div>

            {/* Summary row: days ahead + avg daily alpha */}
            {summary.total_days_compared > 0 && (
              <div className="text-[12px] text-muted-foreground tabular-nums">
                Ahead on {summary.days_portfolio_ahead}/{summary.total_days_compared} days
                {summary.avg_daily_alpha_pp !== 0 && (
                  <span className={`ml-1.5 ${summary.avg_daily_alpha_pp >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                    · avg daily {summary.avg_daily_alpha_pp >= 0 ? "+" : ""}{summary.avg_daily_alpha_pp.toFixed(2)}pp
                  </span>
                )}
              </div>
            )}

            <MergedChart data={chartData} />

            {data.caveats.length > 0 && (
              <div className="flex items-start gap-2 text-[12px] text-muted-foreground bg-muted/40 rounded-xl p-3">
                <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  {data.caveats.map((c, i) => <div key={i}>{c}</div>)}
                </div>
              </div>
            )}
          </>
        )}

        <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Counted vs. excluded symbols</DialogTitle>
            </DialogHeader>
            {data && (
              <div className="space-y-5">
                <section>
                  <h4 className="text-[13px] font-semibold mb-2 flex items-center gap-2">
                    Counted ({data.counted_symbols.length})
                    <span className="text-[11px] text-muted-foreground font-normal">— these drive the line against S&amp;P 500</span>
                  </h4>
                  {data.counted_symbols.length === 0 ? (
                    <p className="text-[12px] text-muted-foreground">None.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {data.counted_symbols.map((s: BenchmarkCountedSymbol) => (
                        <div key={s.symbol} className="flex items-center justify-between text-[13px] py-1.5 px-2 rounded-lg hover:bg-muted/40">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold w-[72px]">{s.symbol}</span>
                            <AssetTypePill type={s.asset_type} source={s.source} />
                            <span className="text-[11px] text-muted-foreground">
                              {s.active_from}{s.active_to ? ` → ${s.active_to}` : " → now"}
                            </span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className={`text-[12px] tabular-nums font-medium ${s.contribution_pp >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
                              {s.contribution_pp >= 0 ? "+" : ""}{s.contribution_pp.toFixed(2)}pp
                            </span>
                            <span className="text-[12px] tabular-nums text-muted-foreground">{s.current_qty} sh</span>
                            <button
                              onClick={() => setClassifyOpen({ symbol: s.symbol, currentType: s.asset_type })}
                              className="text-[11px] text-primary hover:underline"
                            >
                              reclassify
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section>
                  <h4 className="text-[13px] font-semibold mb-2">Excluded ({data.excluded_symbols.length})</h4>
                  {data.excluded_symbols.length === 0 ? (
                    <p className="text-[12px] text-muted-foreground">None.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {data.excluded_symbols.map((s: BenchmarkExcludedSymbol) => (
                        <div key={`${s.symbol}-${s.reason}`} className="flex items-center justify-between text-[13px] py-1.5 px-2 rounded-lg hover:bg-muted/40">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold w-[72px]">{s.symbol}</span>
                            <AssetTypePill type={s.asset_type} source={s.source} />
                            <span className="text-[11px] text-muted-foreground">
                              {s.reason === "classified_non_equity" ? "not an individual stock" :
                               s.reason === "saxo_only" ? "Saxo-synced, no tx history" :
                               s.reason === "closed_before_window" ? "sold before this window" :
                               s.reason === "closed" ? "sold during window" : s.reason}
                            </span>
                          </div>
                          <button
                            onClick={() => setClassifyOpen({ symbol: s.symbol, currentType: s.asset_type })}
                            className="text-[11px] text-primary hover:underline"
                          >
                            reclassify
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={classifyOpen !== null} onOpenChange={(open) => !open && setClassifyOpen(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Classify {classifyOpen?.symbol}</DialogTitle>
            </DialogHeader>
            <p className="text-[13px] text-muted-foreground">
              Pick the asset type. "Equity" counts in the S&amp;P 500 comparison; everything else is excluded.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {ASSET_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => handleReclassify(t)}
                  className={`p-3 rounded-xl border-2 text-left transition ${
                    classifyOpen?.currentType === t
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold capitalize">{t}</span>
                    {classifyOpen?.currentType === t && <span className="text-[10px] text-primary">current</span>}
                  </div>
                </button>
              ))}
            </div>
          </DialogContent>
        </Dialog>
      </GlassCard>
    </>
  );
}
