"use client";

import { motion } from "motion/react";
import { TrendingUp, Loader2 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { formatCurrency } from "@/lib/format";
import { useOverviewQuery } from "@/hooks/queries";

export function BudgetHealthWidget() {
  const { data, isLoading } = useOverviewQuery();
  const budgets = data?.budget_health ?? [];

  return (
    <GlassCard>
      <h2 className="text-[16px] font-semibold mb-5">Budget Health</h2>
      {isLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : budgets.length === 0 ? (
        <div className="text-center py-12">
          <TrendingUp className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" strokeWidth={1.2} />
          <p className="text-muted-foreground">No budgets set</p>
          <p className="text-[12px] text-muted-foreground/60 mt-1">Create a budget in Budgets</p>
        </div>
      ) : (
        <div className="space-y-5">
          {budgets.slice(0, 5).map((b, i) => {
            const pct = b.amount ? (b.spent / b.amount) * 100 : 0;
            const over = pct > 100;
            return (
              <motion.div key={b.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[12px] font-medium">{b.name}</span>
                  <span className="font-mono tabular-nums text-[12px] text-muted-foreground">
                    {formatCurrency(b.spent)} / {formatCurrency(b.amount)}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-secondary overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(pct, 100)}%` }}
                    transition={{ duration: 0.8, delay: 0.05 + i * 0.05, ease: [0.25, 0.46, 0.45, 0.94] }}
                    className="h-full rounded-full"
                    style={{ background: over ? "linear-gradient(90deg, #ef4444, #f97316)" : "linear-gradient(90deg, #2f5bff, #8b5cf6)" }}
                  />
                </div>
                {over && (
                  <p className="text-[11px] text-red-500 mt-1 font-medium">Over budget by {formatCurrency(b.spent - b.amount)}</p>
                )}
              </motion.div>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}
