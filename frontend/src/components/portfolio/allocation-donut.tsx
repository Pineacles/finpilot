"use client";

import { useMemo } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { GlassCard } from "@/components/glass-card";
import { formatCurrency } from "@/lib/format";
import type { Position } from "@/lib/types";

const COLORS = ["#3b82f6", "#f97316", "#a855f7", "#14b8a6", "#f59e0b", "#ec4899", "#22c55e", "#06b6d4", "#8b5cf6", "#e11d48"];
const OTHER_COLOR = "#94a3b8";
// Positions individually smaller than this share of total value get folded
// into a single "Other" slice so the donut stays legible.
const OTHER_THRESHOLD_PCT = 3;

interface AllocationDonutProps {
  positions: Position[];
  delay?: number;
}

export function AllocationDonut({ positions, delay = 0.2 }: AllocationDonutProps) {
  const slices = useMemo(() => {
    const held = positions.filter((p) => p.market_value > 0);
    const total = held.reduce((sum, p) => sum + p.market_value, 0);
    if (!total) return [];

    const big = held.filter((p) => (p.market_value / total) * 100 >= OTHER_THRESHOLD_PCT);
    const small = held.filter((p) => (p.market_value / total) * 100 < OTHER_THRESHOLD_PCT);
    const sorted = [...big].sort((a, b) => b.market_value - a.market_value);
    const otherValue = small.reduce((sum, p) => sum + p.market_value, 0);

    const out = sorted.map((p) => ({ name: p.symbol, value: p.market_value }));
    if (otherValue > 0) {
      out.push({ name: `Other (${small.length})`, value: otherValue });
    }
    return out;
  }, [positions]);

  return (
    <GlassCard delay={delay} className="!p-4">
      <p className="text-[13px] font-medium text-muted-foreground mb-3">Allocation</p>
      {slices.length === 0 ? (
        <p className="text-[13px] text-muted-foreground text-center py-8">No positions</p>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={slices} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} innerRadius={42}>
                {slices.map((s, i) => (
                  <Cell key={s.name} fill={s.name.startsWith("Other") ? OTHER_COLOR : COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: any) => formatCurrency(Number(v))} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </GlassCard>
  );
}
