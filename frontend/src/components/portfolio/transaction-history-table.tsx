"use client";

import { History, LineChart } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { formatCurrency } from "@/lib/format";
import type { Trade } from "@/lib/types";

interface TransactionHistoryTableProps {
  trades: Trade[];
  onOpenChart: (symbol: string) => void;
}

const TYPE_STYLES: Record<string, string> = {
  buy: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  sell: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400",
  deposit: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  withdraw: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
};

export function TransactionHistoryTable({ trades, onOpenChart }: TransactionHistoryTableProps) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-2xl bg-violet-100 dark:bg-violet-500/15 flex items-center justify-center"><History className="h-5 w-5 text-violet-600 dark:text-violet-400" strokeWidth={1.8} /></div>
        <h2 className="text-[16px] font-semibold">Transaction History</h2>
        <span className="text-[13px] text-muted-foreground ml-auto">{trades.length} transactions</span>
      </div>
      {trades.length === 0 ? (
        <GlassCard delay={0.45}><p className="text-muted-foreground py-6 text-center">No transactions yet. Record trades above or let your AI agent log them.</p></GlassCard>
      ) : (
        <GlassCard delay={0.45} className="!p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Date</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Symbol</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Type</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Qty</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Price</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Fees</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-right">Total (CHF)</th>
                  <th className="px-5 py-3.5 text-[12px] font-semibold text-muted-foreground uppercase tracking-wider text-center">Chart</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-border/50 hover:bg-accent/50 transition-colors">
                    <td className="px-5 py-3 text-[13px] tabular-nums text-muted-foreground">{new Date(t.date).toLocaleDateString("en-CH", { day: "numeric", month: "short", year: "numeric" })}</td>
                    <td className="px-5 py-3 text-[14px] font-semibold">{t.symbol}</td>
                    <td className="px-5 py-3"><span className={`text-[12px] px-2.5 py-1 rounded-lg font-semibold uppercase ${TYPE_STYLES[t.type] || TYPE_STYLES.withdraw}`}>{t.type}</span></td>
                    <td className="px-5 py-3 text-[13px] tabular-nums text-right">{t.quantity}</td>
                    <td className="px-5 py-3 text-[13px] tabular-nums text-right"><span>{t.price.toFixed(2)}</span>{t.currency !== "CHF" && <span className="text-[11px] text-muted-foreground ml-1">{t.currency}</span>}</td>
                    <td className="px-5 py-3 text-[13px] tabular-nums text-right text-muted-foreground">{t.fees > 0 ? formatCurrency(t.fees_chf) : "-"}</td>
                    <td className="px-5 py-3 text-[14px] font-medium tabular-nums text-right">{formatCurrency(t.total_chf)}</td>
                    <td className="px-5 py-3 text-center">{t.symbol !== "CASH" && <button onClick={() => onOpenChart(t.symbol)} className="p-1.5 rounded-lg hover:bg-accent transition-colors cursor-pointer" title={`Chart for ${t.symbol}`}><LineChart className="h-4 w-4 text-primary" /></button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
