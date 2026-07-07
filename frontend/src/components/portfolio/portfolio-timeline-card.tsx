"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, CartesianGrid, ComposedChart, Line, Bar } from "recharts";
import { GlassCard } from "@/components/glass-card";
import { RangeSwitcher } from "@/components/range-switcher";
import { formatCurrency } from "@/lib/format";
import type { ValueTimelinePoint } from "@/lib/types";

const TIMELINE_RANGES = ["1W", "1M", "3M", "6M", "1Y", "ALL"] as const;
type TimelineRange = (typeof TIMELINE_RANGES)[number];
const DAYS_MAP: Record<TimelineRange, number> = { "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, ALL: 10000 };

interface PortfolioTimelineCardProps {
  timeline: ValueTimelinePoint[];
}

export function PortfolioTimelineCard({ timeline }: PortfolioTimelineCardProps) {
  const [timelineRange, setTimelineRange] = useState<TimelineRange>("3M");
  if (timeline.length === 0) return null;

  const allChartData = timeline.map((pt, i) => {
    const prev = i > 0 ? timeline[i - 1] : pt;
    const dailyChange = pt.value - prev.value;
    const tradeLabels = pt.trades?.map((t) => {
      if (t.symbol === "CASH") return `${t.type === "deposit" ? "+ Deposit" : "- Withdraw"} ${formatCurrency(t.quantity)}`;
      return `${t.type === "buy" ? "+ Buy" : "- Sell"} ${t.quantity} ${t.symbol} @ ${t.price.toFixed(2)}`;
    }).join("\n") || null;
    return { date: pt.date, value: pt.value, cost: pt.cost, pnl: pt.pnl, dailyChange, gain: dailyChange >= 0 ? dailyChange : 0, loss: dailyChange < 0 ? dailyChange : 0, tradeLabels, trades: pt.trades };
  });

  const days = DAYS_MAP[timelineRange];
  const chartData = allChartData.slice(Math.max(0, allChartData.length - days));
  const lastPt = timeline[timeline.length - 1];
  const rangeFirst = chartData[0];
  const rangeLast = chartData[chartData.length - 1];
  const totalReturn = rangeLast ? rangeLast.value - rangeFirst.value : 0;
  const totalReturnPct = rangeFirst && rangeFirst.value > 0 ? (rangeLast.value / rangeFirst.value - 1) * 100 : 0;

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-2xl bg-indigo-100 dark:bg-indigo-500/15 flex items-center justify-center"><BarChart3 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" strokeWidth={1.8} /></div>
          <h2 className="text-[16px] font-semibold">Portfolio Timeline</h2>
        </div>
        <div className="sm:ml-auto flex items-center gap-3">
          <span className="text-[13px] text-muted-foreground">Current</span>
          <span className="text-[20px] font-bold tabular-nums font-mono">{formatCurrency(lastPt.value)}</span>
          <span className={`text-[13px] font-semibold ${totalReturn >= 0 ? "text-gain" : "text-loss"}`}>{totalReturn >= 0 ? "+" : ""}{formatCurrency(totalReturn)} ({totalReturnPct >= 0 ? "+" : ""}{totalReturnPct.toFixed(1)}%)</span>
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
                <linearGradient id="sg-tl-gain" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22c55e" stopOpacity={0.15} /><stop offset="100%" stopColor="#22c55e" stopOpacity={0} /></linearGradient>
                <linearGradient id="sg-tl-loss" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ef4444" stopOpacity={0.15} /><stop offset="100%" stopColor="#ef4444" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} stroke="var(--muted-foreground)" />
              <YAxis yAxisId="value" tick={{ fontSize: 10 }} domain={["auto", "auto"]} stroke="var(--muted-foreground)" tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0))} />
              <YAxis yAxisId="change" orientation="right" tick={{ fontSize: 9 }} stroke="var(--muted-foreground)" tickFormatter={(v: number) => (v >= 1000 || v <= -1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0))} width={45} />
              <Tooltip content={({ active, payload, label }: any) => {
                if (!active || !payload?.length) return null;
                const d = payload[0]?.payload;
                const change = d?.dailyChange ?? 0;
                return (
                  <div className="bg-popover border border-border rounded-xl p-3 shadow-lg text-[13px] space-y-1 max-w-[260px]">
                    <p className="font-medium">{new Date(String(label)).toLocaleDateString("en-CH", { day: "numeric", month: "short", year: "numeric" })}</p>
                    <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Value</span><span className="font-semibold tabular-nums">{formatCurrency(d?.value ?? 0)}</span></div>
                    <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Cost</span><span className="tabular-nums">{formatCurrency(d?.cost ?? 0)}</span></div>
                    <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">P&L</span><span className={`font-semibold tabular-nums ${(d?.pnl ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>{(d?.pnl ?? 0) >= 0 ? "+" : ""}{formatCurrency(d?.pnl ?? 0)}</span></div>
                    <div className="flex items-center justify-between gap-4"><span className="text-muted-foreground">Day</span><span className={`font-medium tabular-nums ${change >= 0 ? "text-gain" : "text-loss"}`}>{change >= 0 ? "+" : ""}{formatCurrency(change)}</span></div>
                    {d?.tradeLabels && <div className="pt-1.5 mt-1.5 border-t border-border space-y-0.5">{d.tradeLabels.split("\n").map((line: string, i: number) => <p key={i} className={`text-[12px] font-medium ${line.startsWith("+") ? (line.includes("Deposit") ? "text-blue-500" : "text-gain") : line.includes("Withdraw") ? "text-amber-500" : "text-loss"}`}>{line}</p>)}</div>}
                  </div>
                );
              }} />
              <Bar yAxisId="change" dataKey="gain" fill="#22c55e" opacity={0.5} radius={[2, 2, 0, 0]} barSize={3} />
              <Bar yAxisId="change" dataKey="loss" fill="#ef4444" opacity={0.5} radius={[0, 0, 2, 2]} barSize={3} />
              <Area yAxisId="value" type="monotone" dataKey="value" stroke={lastPt.pnl >= 0 ? "#22c55e" : "#ef4444"} strokeWidth={2} fill={lastPt.pnl >= 0 ? "url(#sg-tl-gain)" : "url(#sg-tl-loss)"} />
              <Line yAxisId="value" type="monotone" dataKey="cost" stroke="var(--muted-foreground)" strokeWidth={1} strokeDasharray="4 3" dot={false} />
              {timeline.filter((pt) => pt.trades && pt.trades.length > 0 && chartData.some((cd) => cd.date === pt.date)).map((pt, i) => {
                const t = pt.trades![0];
                const color = t.symbol === "CASH" ? (t.type === "deposit" ? "#3b82f6" : "#f59e0b") : t.type === "buy" ? "#22c55e" : "#ef4444";
                return <ReferenceLine key={`tl-${i}`} yAxisId="value" x={pt.date} stroke={color} strokeDasharray="3 3" strokeWidth={1.5} />;
              })}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center gap-4 mt-3 px-1">
          <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-[#22c55e]/70 inline-block" /><span className="text-[11px] text-muted-foreground">Profit</span></div>
          <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-[#ef4444]/70 inline-block" /><span className="text-[11px] text-muted-foreground">Loss</span></div>
          <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-muted-foreground" /><span className="text-[11px] text-muted-foreground">Cost basis</span></div>
          <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#22c55e]" /><span className="text-[11px] text-muted-foreground">Buy</span></div>
          <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#ef4444]" /><span className="text-[11px] text-muted-foreground">Sell</span></div>
          <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#3b82f6]" /><span className="text-[11px] text-muted-foreground">Deposit</span></div>
          <div className="flex items-center gap-1.5"><span className="w-4 h-0 inline-block border-t-2 border-dashed border-[#f59e0b]" /><span className="text-[11px] text-muted-foreground">Withdraw</span></div>
          <span className="text-[11px] text-muted-foreground ml-auto">Showing {timelineRange === "ALL" ? "all history" : `last ${timelineRange}`}</span>
        </div>
      </GlassCard>
    </div>
  );
}
