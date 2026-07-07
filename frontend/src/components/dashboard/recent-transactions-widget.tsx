"use client";

import { motion } from "motion/react";
import { Banknote, Loader2 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { CategoryPill } from "@/components/category-pill";
import { formatCurrency } from "@/lib/format";
import { useOverviewQuery } from "@/hooks/queries";

export function RecentTransactionsWidget() {
  const { data, isLoading } = useOverviewQuery();
  const recent = data?.recent_transactions ?? [];

  return (
    <GlassCard>
      <h2 className="text-[16px] font-semibold mb-5">Recent Transactions</h2>
      {isLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : recent.length === 0 ? (
        <div className="text-center py-12">
          <Banknote className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" strokeWidth={1.2} />
          <p className="text-muted-foreground">No transactions yet</p>
          <p className="text-[12px] text-muted-foreground/60 mt-1">Import a bank statement to get started</p>
        </div>
      ) : (
        <div className="space-y-3">
          {recent.map((t, i) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05, duration: 0.3 }}
              className="flex items-center justify-between py-1"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`h-10 w-10 rounded-[13px] flex items-center justify-center text-[14px] font-bold flex-shrink-0 ${
                    t.amount < 0
                      ? "bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400"
                      : "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400"
                  }`}
                >
                  {t.merchant.charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="text-[14px] font-medium leading-snug font-sans">{t.merchant}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[12px] text-muted-foreground">{t.date}</span>
                    {t.category_name && <CategoryPill name={t.category_name} />}
                  </div>
                </div>
              </div>
              <p className={`font-mono tabular-nums text-[14px] font-semibold ${t.amount < 0 ? "text-loss" : "text-gain"}`}>
                {formatCurrency(t.amount, t.currency)}
              </p>
            </motion.div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
