"use client";

import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { BarChart3 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { RangeSwitcher } from "@/components/range-switcher";
import type { Position } from "@/lib/types";

const RANGES = [
  { value: "1d", label: "1D" }, { value: "5d", label: "1W" }, { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" }, { value: "6mo", label: "6M" }, { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" }, { value: "5y", label: "5Y" },
];

interface LivePrice { price: number; change: number; change_pct: number }

interface PriceChartCardProps {
  symbol: string | null;
  positions: Position[];
  livePrices: Record<string, LivePrice>;
  fetchChart: (ticker: string, range: string) => Promise<{ date: string; close: number }[]>;
}

export function PriceChartCard({ symbol, positions, livePrices, fetchChart }: PriceChartCardProps) {
  const [range, setRange] = useState("1y");
  const [data, setData] = useState<{ date: string; close: number }[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setLoading(true);
    fetchChart(symbol, range)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, range, fetchChart]);

  const pos = positions.find((p) => p.symbol === symbol);
  const live = symbol ? livePrices[symbol] : undefined;
  const lastPrice = live?.price ?? pos?.last_price ?? 0;
  const change = live?.change ?? pos?.change ?? 0;
  const changePct = live?.change_pct ?? pos?.change_pct ?? 0;

  return (
    <GlassCard delay={0.3} className="md:col-span-2 lg:col-span-2 !p-4">
      <div className="flex items-center justify-center mb-2">
        <p className="text-[13px] font-medium text-muted-foreground flex items-center gap-1.5"><BarChart3 className="h-4 w-4" />{symbol || "Select a holding"}</p>
      </div>
      {!symbol ? (
        <div className="h-60 flex items-center justify-center text-muted-foreground">Click a holding</div>
      ) : (
        <>
          <div className="flex items-center justify-center gap-3 mb-3">
            <span className="font-mono tabular-nums text-[20px] font-bold">{lastPrice.toFixed(2)}</span>
            <span className={`text-[13px] font-semibold ${change >= 0 ? "text-gain" : "text-loss"}`}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(1)}%)
            </span>
          </div>
          <div className="flex justify-center mb-2">
            <RangeSwitcher ranges={RANGES.map((r) => r.label)} active={RANGES.find((r) => r.value === range)?.label || "1Y"} onChange={(lbl) => { const r = RANGES.find((x) => x.label === lbl); if (r) setRange(r.value); }} />
          </div>
          <div className="h-52">
            {loading ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>
            ) : data.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">No data</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <defs>
                    <linearGradient id="price-chart-gradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} stroke="var(--muted-foreground)" />
                  <YAxis hide domain={["auto", "auto"]} />
                  <Tooltip formatter={(v: any) => Number(v).toFixed(2)} />
                  <Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#price-chart-gradient)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </>
      )}
    </GlassCard>
  );
}
