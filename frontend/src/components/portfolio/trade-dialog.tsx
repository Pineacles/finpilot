"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { AlertTriangle } from "lucide-react";
import { api, ApiError, CurrencyMismatchDetail } from "@/lib/api";

const TRADE_TYPES = ["buy", "sell", "deposit", "withdraw"] as const;
type TradeType = (typeof TRADE_TYPES)[number];

const emptyForm = {
  symbol: "", type: "buy" as TradeType, quantity: "", price: "",
  currency: "USD", date: new Date().toISOString().split("T")[0], fees: "",
  deduct_from_cash: true,
};

function isCurrencyMismatch(detail: unknown): detail is CurrencyMismatchDetail {
  return !!detail && typeof detail === "object" && (detail as { error?: string }).error === "currency_mismatch";
}

interface TradeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function TradeDialog({ open, onOpenChange, onSuccess }: TradeDialogProps) {
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [mismatch, setMismatch] = useState<CurrencyMismatchDetail | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setForm(emptyForm);
    setError("");
    setMismatch(null);
  };

  const submit = async (confirmCurrency: boolean) => {
    if (!form.quantity || (form.type !== "deposit" && form.type !== "withdraw" && !form.symbol)) return;
    setSubmitting(true);
    setError("");
    try {
      await api.trade({
        symbol: form.type === "deposit" || form.type === "withdraw" ? "CASH" : form.symbol.toUpperCase().trim(),
        type: form.type,
        quantity: parseFloat(form.quantity),
        price: form.price ? parseFloat(form.price) : undefined,
        currency: form.currency,
        date: form.date || undefined,
        fees: form.fees ? parseFloat(form.fees) : 0,
        deduct_from_cash: form.deduct_from_cash,
        confirm_currency: confirmCurrency,
      });
      reset();
      onOpenChange(false);
      onSuccess();
    } catch (e) {
      if (e instanceof ApiError && isCurrencyMismatch(e.detail)) {
        setMismatch(e.detail);
      } else {
        setError(e instanceof Error ? e.message : "Trade failed");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent className="rounded-3xl">
        <DialogHeader><DialogTitle>Record Trade</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-1.5">
            {TRADE_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => { setForm({ ...form, type: t }); setMismatch(null); }}
                className={`py-2.5 rounded-xl text-[14px] font-medium transition-all cursor-pointer capitalize ${form.type === t ? "bg-primary text-primary-foreground" : "bg-accent text-muted-foreground hover:text-foreground"}`}
              >
                {t}
              </button>
            ))}
          </div>

          {form.type !== "deposit" && form.type !== "withdraw" && (
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Ticker</label>
              <Input placeholder="AAPL, NVDA..." value={form.symbol} onChange={(e) => { setForm({ ...form, symbol: e.target.value }); setMismatch(null); }} className="rounded-xl h-11" />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">{form.type === "deposit" || form.type === "withdraw" ? "Amount" : "Qty"}</label>
              <Input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} className="rounded-xl h-11" />
            </div>
            {form.type !== "deposit" && form.type !== "withdraw" && (
              <div>
                <label className="text-[13px] text-muted-foreground block mb-1.5">Price</label>
                <Input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="rounded-xl h-11" placeholder="Market" />
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Date</label>
              <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="rounded-xl h-11" />
            </div>
            <div>
              <label className="text-[13px] text-muted-foreground block mb-1.5">Currency</label>
              <select className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] border-0" value={form.currency} onChange={(e) => { setForm({ ...form, currency: e.target.value }); setMismatch(null); }}>
                {["USD", "CHF", "EUR", "GBP", "KRW"].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {mismatch && (
            <div className="rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3.5 space-y-2.5">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                <p className="text-[12.5px] text-amber-800 dark:text-amber-300 leading-snug">{mismatch.message}</p>
              </div>
              <button
                onClick={() => submit(true)}
                disabled={submitting}
                className="w-full h-9 rounded-xl bg-amber-600 text-white text-[13px] font-semibold hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
              >
                Use {mismatch.quote_currency} instead
              </button>
            </div>
          )}

          {error && <p className="text-[13px] text-loss">{error}</p>}

          <button
            onClick={() => submit(false)}
            disabled={submitting}
            className="w-full h-11 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer capitalize disabled:opacity-50"
          >
            {submitting ? "Processing..." : form.type}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
