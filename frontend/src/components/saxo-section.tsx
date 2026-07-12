"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/glass-card";
import { PlugZap, RefreshCw, Building2 } from "lucide-react";
import { api, type SaxoSubPortfolio } from "@/lib/api";

export function SaxoSection() {
  const [sub, setSub] = useState<SaxoSubPortfolio | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSub(await api.saxoSubPortfolio());
    } catch {
      setSub({ connected: false, accounts: [] });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!sub || !sub.connected || sub.accounts.length === 0) {
    return null;
  }

  const account = sub.accounts[0];

  const handleSync = async () => {
    setSyncing(true); setSyncError(null);
    try {
      await api.saxoSync();
      await load();
    } catch (e) {
      setSyncError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const positionsValueLocal = account.positions.reduce((sum, p) => sum + p.market_value, 0);

  return (
    <div>
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-2xl bg-sky-100 dark:bg-sky-500/15 flex items-center justify-center">
          <Building2 className="h-5 w-5 text-sky-600 dark:text-sky-400" strokeWidth={1.8} />
        </div>
        <h2 className="text-[16px] font-semibold">Saxo Brokerage</h2>
        <span className="text-[12px] px-2 py-0.5 rounded-full bg-accent text-muted-foreground font-medium">
          {account.positions.length} position{account.positions.length === 1 ? "" : "s"}
        </span>
      </div>
      <GlassCard delay={0.48}>
      <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-500 flex items-center justify-center">
            <PlugZap className="h-5 w-5 text-white" />
          </div>
          <div>
            <h2 className="text-[16px] font-semibold">{account.name}</h2>
            <p className="text-[12px] text-muted-foreground">
              Broker-synced (read-only) · {account.positions.length} position{account.positions.length === 1 ? "" : "s"} ·
              cash updated {account.cash_updated_at ? new Date(account.cash_updated_at).toLocaleTimeString() : "—"}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSync} disabled={syncing} className="rounded-xl">
            <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing ? "animate-spin" : ""}`} />
            Sync
          </Button>
        </div>
      </div>

      {syncError && (
        <div className="mb-4 rounded-xl px-3 py-2 text-[13px] bg-red-500/10 text-red-600 dark:text-red-400">
          {syncError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 mb-5">
        <div className="p-4 rounded-2xl bg-muted/60">
          <p className="text-[12px] text-muted-foreground mb-1 uppercase tracking-wide">Cash</p>
          <p className="font-mono tabular-nums text-[22px] font-semibold">
            {account.cash.toLocaleString(undefined, { maximumFractionDigits: 2 })}{" "}
            <span className="text-[13px] text-muted-foreground">{account.currency}</span>
          </p>
        </div>
        <div className="p-4 rounded-2xl bg-muted/60">
          <p className="text-[12px] text-muted-foreground mb-1 uppercase tracking-wide">Positions value</p>
          <p className="font-mono tabular-nums text-[22px] font-semibold">
            {positionsValueLocal.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      {account.positions.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-border">
          <table className="w-full text-[13px]">
            <thead className="bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left">Symbol</th>
                <th className="px-4 py-2 text-left">Name</th>
                <th className="px-4 py-2 text-right">Qty</th>
                <th className="px-4 py-2 text-right">Avg cost</th>
                <th className="px-4 py-2 text-right">Last</th>
                <th className="px-4 py-2 text-right">Market value</th>
                <th className="px-4 py-2 text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {account.positions.map(p => (
                <tr key={p.id} className="border-t border-border">
                  <td className="px-4 py-2.5 font-semibold">{p.symbol}</td>
                  <td className="px-4 py-2.5 text-muted-foreground truncate max-w-[220px]">{p.name}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums">{p.quantity}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums">{p.avg_cost_price.toFixed(2)} <span className="text-muted-foreground text-[11px]">{p.currency}</span></td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums">{p.last_price ? p.last_price.toFixed(2) : "—"}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums">{p.market_value.toFixed(2)}</td>
                  <td className={`px-4 py-2.5 text-right font-mono tabular-nums ${(p.unrealized_pnl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                    {p.unrealized_pnl !== null ? (p.unrealized_pnl >= 0 ? "+" : "") + p.unrealized_pnl.toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </GlassCard>
    </div>
  );
}
