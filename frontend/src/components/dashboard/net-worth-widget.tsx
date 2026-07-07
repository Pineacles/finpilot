"use client";

import { Wallet, Loader2 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { AnimatedNumber } from "@/components/animated-number";
import { formatCurrency } from "@/lib/format";
import { useOverviewQuery } from "@/hooks/queries";

/** Big "at a glance" net worth number — bank + credit card + portfolio. */
export function NetWorthWidget() {
  const { data, isLoading } = useOverviewQuery();

  return (
    <GlassCard className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute -top-10 -right-10 h-[140px] w-[140px] rounded-full opacity-35 blur-[40px]"
        style={{ background: "linear-gradient(135deg, #16a34a, #22c55e)" }}
      />
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-5">
          <div className="h-[44px] w-[44px] rounded-[14px] bg-emerald-100 dark:bg-emerald-500/15 flex items-center justify-center">
            <Wallet className="h-6 w-6 text-emerald-600 dark:text-emerald-400" strokeWidth={1.8} />
          </div>
        </div>
        <p className="text-[12px] font-medium text-muted-foreground mb-1">Net Worth</p>
        {isLoading || !data ? (
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        ) : (
          <p className="font-mono tabular-nums text-[28px] font-bold" style={{ letterSpacing: "-0.8px" }}>
            <AnimatedNumber value={data.net_worth} format={formatCurrency} />
          </p>
        )}
        <p className="text-[13px] text-muted-foreground mt-2">Bank + credit cards + portfolio</p>
      </div>
    </GlassCard>
  );
}
