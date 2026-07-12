"use client";

import { useMemo, useState } from "react";
import { BarChart3 } from "lucide-react";
import { Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ComposedChart, Line, ReferenceDot } from "recharts";
import { GlassCard } from "@/components/glass-card";
import { RangeSwitcher } from "@/components/range-switcher";
import { formatCurrency } from "@/lib/format";
import type { ValueTimelinePoint } from "@/lib/types";

const TIMELINE_RANGES = ["1W", "1M", "3M", "6M", "1Y", "ALL"] as const;
type TimelineRange = (typeof TIMELINE_RANGES)[number];
const DAYS_MAP: Record<TimelineRange, number> = { "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, ALL: 10000 };

type TradeEntry = NonNullable<ValueTimelinePoint["trades"]>[number];

// Trade-day marker color: a day can mix trade types (e.g. a sell funding a
// buy), so pick one color by priority: sell > buy > deposit/withdraw.
function markerColorFor(trades: ValueTimelinePoint["trades"]): string | null {
  if (!trades || trades.length === 0) return null;
  if (trades.some((t) => t.type === "sell")) return "#ef4444";
  if (trades.some((t) => t.type === "buy")) return "#22c55e";
  return "#3b82f6";
}

function tradeLineLabel(t: TradeEntry): { text: string; color: string } {
  if (t.symbol === "CASH") {
    return t.type === "deposit"
      ? { text: `Deposit ${formatCurrency(t.quantity)}`, color: "text-blue-500" }
      : { text: `Withdraw ${formatCurrency(t.quantity)}`, color: "text-amber-500" };
  }
  return t.type === "buy"
    ? { text: `Buy ${t.quantity} ${t.symbol} @ ${t.price.toFixed(2)}`, color: "text-gain" }
    : { text: `Sell ${t.quantity} ${t.symbol} @ ${t.price.toFixed(2)}`, color: "text-loss" };
}

function compactChf(v: number): string {
  return Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0);
}

interface PortfolioTimelineCardProps {
  timeline: ValueTimelinePoint[];
}

// Shape of one point in `chartData` below: matches what the Tooltip's
// `content` render-prop receives back via `payload[0].payload`.
interface TimelineChartDatum {
  date: string;
  value: number;
  cost: number;
  pnl: number;
  marker: string | null;
  trades: ValueTimelinePoint["trades"];
}

// Minimal structural type for the subset of recharts' Tooltip content props
// this component actually reads (recharts' own generic TooltipContentProps
// is keyed on its internal TooltipPayload type, which doesn't know about
// our chart-specific datum shape).
interface TimelineTooltipContentProps {
  active?: boolean;
  payload?: readonly { payload?: TimelineChartDatum }[];
  label?: string | number;
}

export function PortfolioTimelineCard({ timeline }: PortfolioTimelineCardProps) {
  const [timelineRange, setTimelineRange] = useState<TimelineRange>("3M");

  const allChartData: TimelineChartDatum[] = useMemo(
    () =>
      timeline.map((pt) => ({
        date: pt.date,
        value: pt.value,
        cost: pt.cost,
        pnl: pt.pnl,
        marker: markerColorFor(pt.trades),
        trades: pt.trades,
      })),
    [timeline],
  );

  const days = DAYS_MAP[timelineRange];
  const chartData = useMemo(
    () => allChartData.slice(Math.max(0, allChartData.length - days)),
    [allChartData, days],
  );

  // Single shared y-axis domain: padded to whatever is visible (value and
  // cost together, since both plot on it), never zero-anchored or forced
  // symmetric.
  const yDomain = useMemo<[number, number]>(() => {
    if (chartData.length === 0) return [0, 1];
    let min = Infinity;
    let max = -Infinity;
    for (const d of chartData) {
      if (d.value < min) min = d.value;
      if (d.value > max) max = d.value;
      if (d.cost < min) min = d.cost;
      if (d.cost > max) max = d.cost;
    }
    const span = max - min || Math.abs(max) || 1;
    return [min - span * 0.04, max + span * 0.04];
  }, [chartData]);

  if (timeline.length === 0) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-5">
          <div className="h-10 w-10 rounded-2xl bg-indigo-100 dark:bg-indigo-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" strokeWidth={1.8} /></div>
          <h2 className="text-[16px] font-semibold">Portfolio Timeline</h2>
        </div>
        <GlassCard delay={0.42} className="!p-4">
          <div className="h-60 flex flex-col items-center justify-center gap-2 text-muted-foreground">
            <BarChart3 className="h-8 w-8 opacity-30" />
            <p className="text-[13px]">No trades yet. Record a trade or deposit to see your timeline.</p>
          </div>
        </GlassCard>
      </div>
    );
  }

  const lastPt = timeline[timeline.length - 1];
  const rangeFirst = chartData[0];
  const rangeLast = chartData[chartData.length - 1];

  const rangeChangeChf = rangeLast.value - rangeFirst.value;
  const rangeChangePct = rangeFirst.value !== 0 ? (rangeLast.value / rangeFirst.value - 1) * 100 : 0;
  const suppressRangePct = rangeFirst.value < 100;
  const trendUp = rangeLast.value >= rangeFirst.value;
  const trendColor = trendUp ? "#22c55e" : "#ef4444";

  const allTimePnl = lastPt.pnl;
  const allTimePnlPct = lastPt.cost > 0 ? (lastPt.pnl / lastPt.cost) * 100 : 0;

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-indigo-100 dark:bg-indigo-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" strokeWidth={1.8} /></div>
          <h2 className="text-[16px] font-semibold">Portfolio Timeline</h2>
        </div>
        <div className="sm:ml-auto flex flex-wrap items-center gap-x-5 gap-y-1">
          <div className="flex items-baseline gap-2">
            <span className="text-[13px] text-muted-foreground">Current</span>
            <span className="text-[20px] font-bold tabular-nums font-mono">{formatCurrency(lastPt.value)}</span>
          </div>
          <div className="flex flex-col items-end leading-tight">
            <span className={`text-[13px] font-semibold tabular-nums ${rangeChangeChf >= 0 ? "text-gain" : "text-loss"}`}>
              {rangeChangeChf >= 0 ? "+" : ""}{formatCurrency(rangeChangeChf)}
              {!suppressRangePct && ` (${rangeChangePct >= 0 ? "+" : ""}${rangeChangePct.toFixed(1)}%)`}
            </span>
            <span className="text-[10px] text-muted-foreground">{timelineRange.toLowerCase()} change</span>
          </div>
          <div className="flex flex-col items-end leading-tight">
            <span className={`text-[13px] font-semibold tabular-nums ${allTimePnl >= 0 ? "text-gain" : "text-loss"}`}>
              {allTimePnl >= 0 ? "+" : ""}{formatCurrency(allTimePnl)} ({allTimePnlPct >= 0 ? "+" : ""}{allTimePnlPct.toFixed(1)}%)
            </span>
            <span className="text-[10px] text-muted-foreground">vs deposits</span>
          </div>
        </div>
      </div>
      <GlassCard delay={0.42} className="!p-4">
        <div className="flex justify-center mb-3">
          <RangeSwitcher ranges={[...TIMELINE_RANGES]} active={timelineRange} onChange={(r) => setTimelineRange(r as TimelineRange)} />
        </div>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="sg-tl-gain" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22c55e" stopOpacity={0.25} /><stop offset="100%" stopColor="#22c55e" stopOpacity={0} /></linearGradient>
                <linearGradient id="sg-tl-loss" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ef4444" stopOpacity={0.25} /><stop offset="100%" stopColor="#ef4444" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} stroke="var(--muted-foreground)" />
              <YAxis tick={{ fontSize: 10 }} domain={yDomain} stroke="var(--muted-foreground)" tickFormatter={compactChf} width={44} />
              <Tooltip
                cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
                content={({ active, payload, label }: TimelineTooltipContentProps) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload;
                  if (!d) return null;
                  return (
                    <div className="bg-popover border border-border rounded-xl p-3 shadow-lg text-[12px] space-y-1 max-w-[260px]">
                      <p className="font-medium text-[13px]">{new Date(String(label)).toLocaleDateString("en-CH", { day: "numeric", month: "short", year: "numeric" })}</p>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Value</span><span className="font-semibold tabular-nums">{formatCurrency(d.value)}</span></div>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Deposited</span><span className="tabular-nums">{formatCurrency(d.cost)}</span></div>
                      <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">P&L</span><span className={`font-semibold tabular-nums ${d.pnl >= 0 ? "text-gain" : "text-loss"}`}>{d.pnl >= 0 ? "+" : ""}{formatCurrency(d.pnl)}</span></div>
                      {d.trades && d.trades.length > 0 && (
                        <div className="pt-1.5 mt-1.5 border-t border-border space-y-0.5">
                          {d.trades.map((t, i) => {
                            const { text, color } = tradeLineLabel(t);
                            return <p key={i} className={`text-[12px] font-medium ${color}`}>{text}</p>;
                          })}
                        </div>
                      )}
                    </div>
                  );
                }}
              />
              <Area type="monotone" dataKey="value" stroke={trendColor} strokeWidth={2} fill={trendUp ? "url(#sg-tl-gain)" : "url(#sg-tl-loss)"} isAnimationActive={false} />
              <Line type="stepAfter" dataKey="cost" stroke="var(--muted-foreground)" strokeWidth={1} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              {chartData.filter((d) => d.marker).map((d) => (
                <ReferenceDot key={`marker-${d.date}`} x={d.date} y={d.value} r={3.5} fill={d.marker!} stroke="var(--background)" strokeWidth={1.5} ifOverflow="visible" />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center gap-4 mt-3 px-1">
          <div className="flex items-center gap-1.5"><span className="w-4 h-0.5 rounded-full inline-block" style={{ backgroundColor: trendColor }} /><span className="text-[11px] text-muted-foreground">Value</span></div>
          <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-muted-foreground" /><span className="text-[11px] text-muted-foreground">Cost basis</span></div>
          <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full inline-block bg-[#22c55e]" /><span className="text-[11px] text-muted-foreground">Buy</span></div>
          <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full inline-block bg-[#ef4444]" /><span className="text-[11px] text-muted-foreground">Sell</span></div>
          <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full inline-block bg-[#3b82f6]" /><span className="text-[11px] text-muted-foreground">Deposit / Withdraw</span></div>
          <span className="text-[11px] text-muted-foreground ml-auto">Showing {timelineRange === "ALL" ? "all history" : `last ${timelineRange}`}</span>
        </div>
      </GlassCard>
    </div>
  );
}
