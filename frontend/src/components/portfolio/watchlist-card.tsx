"use client";

import { useCallback, useState } from "react";
import { Eye, Plus, X, Loader2 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { Input } from "@/components/ui/input";
import { LivePill } from "@/components/live-pill";
import { api, ApiError } from "@/lib/api";
import { useVisibleInterval } from "@/hooks/use-visible-interval";
import type { WatchlistItem } from "@/lib/types";

// Tracking only — deliberately no analysis, no buy/sell signal, no
// recommendations here. Just "what price is X at right now."
export function WatchlistCard() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [symbolInput, setSymbolInput] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.watchlist();
      setItems(data);
    } catch {
      // keep last-known list rather than blanking it on a transient failure
    } finally {
      setLoaded(true);
    }
  }, []);

  const live = useVisibleInterval(load, 30000);

  const handleAdd = async () => {
    const symbol = symbolInput.trim().toUpperCase();
    if (!symbol) return;
    setAdding(true);
    setError("");
    try {
      const item = await api.addWatchlistItem(symbol);
      setItems((prev) => [...prev, item]);
      setSymbolInput("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add symbol");
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (symbol: string) => {
    setItems((prev) => prev.filter((i) => i.symbol !== symbol));
    try {
      await api.removeWatchlistItem(symbol);
    } catch {
      load(); // resync on failure rather than leaving an inconsistent optimistic state
    }
  };

  return (
    <GlassCard delay={0.35} className="!p-4">
      <div className="flex items-center gap-2 mb-3">
        <Eye className="h-4 w-4 text-muted-foreground" />
        <p className="text-[14px] font-semibold text-muted-foreground">Watchlist</p>
        <span className="text-[11px] text-muted-foreground">tracking only, no recommendations</span>
        <LivePill live={live} className="ml-auto" />
      </div>

      <div className="flex gap-2 mb-3">
        <Input
          value={symbolInput}
          onChange={(e) => setSymbolInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="Add ticker, e.g. NVDA"
          className="h-9 rounded-xl text-[13px]"
        />
        <button
          onClick={handleAdd}
          disabled={adding || !symbolInput.trim()}
          className="h-9 w-9 shrink-0 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:brightness-110 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
        >
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
        </button>
      </div>
      {error && <p className="text-[12px] text-loss mb-2">{error}</p>}

      {!loaded ? (
        <p className="text-[12px] text-muted-foreground py-2">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-[12px] text-muted-foreground py-4 text-center">No tickers watched yet.</p>
      ) : (
        <div className="space-y-1 max-h-[220px] overflow-y-auto pr-1">
          {items.map((item) => (
            <div key={item.id} className="flex items-center justify-between px-3 py-2 rounded-xl hover:bg-accent transition-colors group">
              <div className="min-w-0">
                <p className="font-bold text-[13px]">{item.symbol}</p>
                <p className="text-[11px] text-muted-foreground truncate max-w-[140px]">{item.name || "—"}</p>
              </div>
              <div className="flex items-center gap-2">
                {item.quote_unavailable ? (
                  <span className="text-[11px] text-muted-foreground">no quote</span>
                ) : (
                  <div className="text-right">
                    <p className="font-mono tabular-nums text-[13px] font-semibold">
                      {item.price?.toFixed(2)} <span className="text-[10px] text-muted-foreground">{item.currency}</span>
                    </p>
                    <p className={`text-[11px] tabular-nums font-medium ${(item.change_pct ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>
                      {(item.change_pct ?? 0) >= 0 ? "+" : ""}
                      {(item.change_pct ?? 0).toFixed(2)}%
                    </p>
                  </div>
                )}
                <button
                  onClick={() => handleRemove(item.symbol)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-background transition-opacity cursor-pointer"
                  aria-label={`Remove ${item.symbol}`}
                >
                  <X className="h-3.5 w-3.5 text-muted-foreground" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
