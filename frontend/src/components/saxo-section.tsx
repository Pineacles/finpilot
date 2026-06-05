"use client";

import { useCallback, useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { GlassCard } from "@/components/glass-card";
import { PlugZap, RefreshCw, ShoppingCart, X, Building2 } from "lucide-react";
import {
  api,
  type SaxoOrderInput,
  type SaxoOrderSummary,
  type SaxoPrecheckResult,
  type SaxoSubPortfolio,
} from "@/lib/api";

interface TradeDraft {
  symbol: string;
  buy_sell: "Buy" | "Sell";
  amount: string;
  order_type: "Market" | "Limit";
  limit_price: string;
  duration: "DayOrder" | "GoodTillCancel";
}

const EMPTY_DRAFT: TradeDraft = {
  symbol: "",
  buy_sell: "Buy",
  amount: "1",
  order_type: "Market",
  limit_price: "",
  duration: "DayOrder",
};

export function SaxoSection() {
  const [sub, setSub] = useState<SaxoSubPortfolio | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [orders, setOrders] = useState<SaxoOrderSummary[]>([]);
  const [tradeOpen, setTradeOpen] = useState(false);
  const [draft, setDraft] = useState<TradeDraft>(EMPTY_DRAFT);
  const [precheck, setPrecheck] = useState<SaxoPrecheckResult | null>(null);
  const [submitting, setSubmitting] = useState<"precheck" | "place" | null>(null);
  const [tradeError, setTradeError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const p = await api.saxoSubPortfolio();
      setSub(p);
      if (p.connected && p.accounts[0]) {
        const accountKey = _deriveAccountKey(p.accounts[0].name);
        if (accountKey) {
          try { setOrders((await api.saxoListOrders(accountKey)).orders); }
          catch { setOrders([]); }
        }
      }
    } catch (e: any) {
      setSub({ connected: false, accounts: [] });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!sub || !sub.connected || sub.accounts.length === 0) {
    return null;
  }

  const account = sub.accounts[0];
  const accountKey = _deriveAccountKey(account.name) || "";

  const handleSync = async () => {
    setSyncing(true); setSyncError(null);
    try {
      await api.saxoSync();
      await load();
    } catch (e: any) {
      setSyncError(e?.message || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const resetTrade = () => {
    setDraft(EMPTY_DRAFT);
    setPrecheck(null);
    setTradeError(null);
    setSubmitting(null);
  };

  const openTrade = (preset?: Partial<TradeDraft>) => {
    resetTrade();
    setDraft({ ...EMPTY_DRAFT, ...preset });
    setTradeOpen(true);
  };

  const buildOrder = (): SaxoOrderInput | null => {
    const amount = Number(draft.amount);
    if (!draft.symbol.trim() || !amount || amount <= 0) {
      setTradeError("Symbol and quantity > 0 are required.");
      return null;
    }
    if (draft.order_type === "Limit") {
      const lp = Number(draft.limit_price);
      if (!lp || lp <= 0) {
        setTradeError("Limit price is required for Limit orders.");
        return null;
      }
      return {
        account_key: accountKey,
        symbol: draft.symbol.trim().toUpperCase(),
        buy_sell: draft.buy_sell,
        amount,
        order_type: "Limit",
        duration: draft.duration,
        limit_price: lp,
      };
    }
    return {
      account_key: accountKey,
      symbol: draft.symbol.trim().toUpperCase(),
      buy_sell: draft.buy_sell,
      amount,
      order_type: "Market",
      duration: "DayOrder",
    };
  };

  const handlePrecheck = async () => {
    setTradeError(null);
    const order = buildOrder();
    if (!order) return;
    setSubmitting("precheck");
    try {
      const result = await api.saxoPrecheck(order);
      setPrecheck(result);
      if (!result.ok && result.error_message) {
        setTradeError(result.error_message);
      }
    } catch (e: any) {
      setTradeError(e?.message || "Precheck failed");
    } finally {
      setSubmitting(null);
    }
  };

  const handlePlace = async () => {
    setTradeError(null);
    const order = buildOrder();
    if (!order) return;
    setSubmitting("place");
    try {
      await api.saxoPlaceOrder(order);
      setTradeOpen(false);
      resetTrade();
      await load();
    } catch (e: any) {
      setTradeError(e?.message || "Order failed");
    } finally {
      setSubmitting(null);
    }
  };

  const handleCancelOrder = async (orderId: string) => {
    try {
      await api.saxoCancelOrder(orderId, accountKey);
      await load();
    } catch {
      // surfaces next refresh
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
              Broker-synced · {account.positions.length} position{account.positions.length === 1 ? "" : "s"} ·
              cash updated {account.cash_updated_at ? new Date(account.cash_updated_at).toLocaleTimeString() : "—"}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSync} disabled={syncing} className="rounded-xl">
            <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing ? "animate-spin" : ""}`} />
            Sync
          </Button>
          <Button onClick={() => openTrade()} className="rounded-xl">
            <ShoppingCart className="h-4 w-4 mr-1.5" />
            Trade
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
        <div className="overflow-x-auto rounded-2xl border border-border mb-5">
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
                <th className="px-4 py-2"></th>
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
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => openTrade({ symbol: p.symbol, buy_sell: "Sell", amount: String(p.quantity) })}
                      className="text-[11px] px-2 py-1 rounded-lg bg-accent hover:bg-muted transition-colors cursor-pointer"
                    >
                      Close
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {orders.length > 0 && (
        <div className="rounded-2xl border border-border">
          <div className="px-4 py-2 bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
            Working orders
          </div>
          <table className="w-full text-[13px]">
            <tbody>
              {orders.map(o => (
                <tr key={o.order_id} className="border-t border-border">
                  <td className="px-4 py-2.5">
                    <span className="font-semibold">{o.symbol || "—"}</span>
                    <span className="text-[11px] text-muted-foreground ml-2">{o.order_type}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge className={`rounded-lg ${o.buy_sell === "Buy" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" : "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>
                      {o.buy_sell}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums">{o.amount}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-muted-foreground">
                    {o.price !== null ? `@ ${o.price.toFixed(2)}` : ""}
                  </td>
                  <td className="px-4 py-2.5 text-right text-[11px] text-muted-foreground">{o.status}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => handleCancelOrder(o.order_id)}
                      className="p-1 rounded-lg hover:bg-accent transition-colors cursor-pointer"
                      title="Cancel"
                    >
                      <X className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={tradeOpen} onOpenChange={open => { if (!open) { setTradeOpen(false); resetTrade(); } }}>
        <DialogContent className="rounded-3xl max-w-md">
          <DialogHeader><DialogTitle className="flex items-center gap-2">
            <ShoppingCart className="h-5 w-5 text-primary" />Saxo trade
          </DialogTitle></DialogHeader>
          <div className="space-y-3.5">
            <div className="grid grid-cols-2 gap-2">
              {(["Buy", "Sell"] as const).map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => { setDraft({ ...draft, buy_sell: s }); setPrecheck(null); }}
                  className={`py-2.5 rounded-xl text-[14px] font-semibold transition-all cursor-pointer ${draft.buy_sell === s ? (s === "Buy" ? "bg-emerald-500 text-white" : "bg-rose-500 text-white") : "bg-accent text-muted-foreground"}`}
                >{s}</button>
              ))}
            </div>
            <div>
              <label className="text-[12px] uppercase tracking-wide text-muted-foreground block mb-1.5 font-semibold">Symbol</label>
              <Input
                value={draft.symbol}
                onChange={e => { setDraft({ ...draft, symbol: e.target.value }); setPrecheck(null); }}
                placeholder="AAPL"
                className="rounded-xl h-11 font-mono"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[12px] uppercase tracking-wide text-muted-foreground block mb-1.5 font-semibold">Quantity</label>
                <Input
                  type="number"
                  value={draft.amount}
                  onChange={e => { setDraft({ ...draft, amount: e.target.value }); setPrecheck(null); }}
                  className="rounded-xl h-11"
                />
              </div>
              <div>
                <label className="text-[12px] uppercase tracking-wide text-muted-foreground block mb-1.5 font-semibold">Order type</label>
                <select
                  value={draft.order_type}
                  onChange={e => { setDraft({ ...draft, order_type: e.target.value as "Market" | "Limit" }); setPrecheck(null); }}
                  className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] outline-none border border-border"
                >
                  <option value="Market">Market</option>
                  <option value="Limit">Limit</option>
                </select>
              </div>
            </div>
            {draft.order_type === "Limit" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[12px] uppercase tracking-wide text-muted-foreground block mb-1.5 font-semibold">Limit price</label>
                  <Input
                    type="number"
                    value={draft.limit_price}
                    onChange={e => { setDraft({ ...draft, limit_price: e.target.value }); setPrecheck(null); }}
                    className="rounded-xl h-11"
                  />
                </div>
                <div>
                  <label className="text-[12px] uppercase tracking-wide text-muted-foreground block mb-1.5 font-semibold">Duration</label>
                  <select
                    value={draft.duration}
                    onChange={e => { setDraft({ ...draft, duration: e.target.value as "DayOrder" | "GoodTillCancel" }); setPrecheck(null); }}
                    className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] outline-none border border-border"
                  >
                    <option value="DayOrder">Day order</option>
                    <option value="GoodTillCancel">GTC</option>
                  </select>
                </div>
              </div>
            )}

            {precheck && (
              <div className={`rounded-xl p-3 text-[13px] ${precheck.ok ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-red-500/10 text-red-700 dark:text-red-400"}`}>
                {precheck.ok ? (
                  <div className="space-y-1">
                    <p className="font-semibold">Precheck OK</p>
                    {precheck.estimated_cash_required !== null && (
                      <p>Est. cash required: {precheck.estimated_cash_required.toFixed(2)}{precheck.currency ? ` ${precheck.currency}` : ""}</p>
                    )}
                    {precheck.estimated_fees !== null && (
                      <p>Est. fees: {precheck.estimated_fees.toFixed(2)}</p>
                    )}
                    {precheck.warnings.length > 0 && (
                      <ul className="list-disc pl-5">
                        {precheck.warnings.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    )}
                  </div>
                ) : (
                  <p>{precheck.error_message || "Precheck failed"}</p>
                )}
              </div>
            )}

            {tradeError && (
              <p className="text-[13px] text-red-600 dark:text-red-400">{tradeError}</p>
            )}

            <div className="grid grid-cols-2 gap-2 pt-1">
              <Button variant="outline" onClick={handlePrecheck} disabled={submitting !== null} className="rounded-xl h-11">
                {submitting === "precheck" ? "Prechecking…" : "Precheck"}
              </Button>
              <Button
                onClick={handlePlace}
                disabled={submitting !== null || !precheck?.ok}
                className={`rounded-xl h-11 ${draft.buy_sell === "Sell" ? "bg-rose-500 hover:bg-rose-600" : ""}`}
              >
                {submitting === "place" ? "Placing…" : `${draft.buy_sell} ${draft.symbol || ""}`}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </GlassCard>
    </div>
  );
}

/** Extract AccountKey from the synthetic Saxo account name ("Saxo SIM [abc==]"). */
function _deriveAccountKey(name: string): string | null {
  const match = /\[(.+)\]$/.exec(name);
  return match ? match[1] : null;
}
