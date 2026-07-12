"use client";

import { useState } from "react";
import { Pencil, Trash2, Check, X, AlertTriangle } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { Input } from "@/components/ui/input";
import { Sparkline } from "@/components/sparkline";
import { formatCurrency, cn } from "@/lib/format";
import { api } from "@/lib/api";
import type { Position } from "@/lib/types";

const ETF_TYPES = new Set(["etf", "index"]);

// Shared grid template for every holdings row (both sections), so shares /
// price / value columns line up on the same vertical axes no matter which
// row is missing sparkline data or hits the FX-unavailable branch. The
// sparkline track only exists at lg+, where the column is shown.
const ROW_GRID = "grid grid-cols-[minmax(0,1fr)_64px_92px_150px] lg:grid-cols-[minmax(0,1fr)_92px_64px_92px_150px] gap-x-3";

interface LivePrice { price: number; change: number; change_pct: number }

interface HoldingsTableProps {
  positions: Position[];
  livePrices: Record<string, LivePrice>;
  flashes: Record<string, "up" | "down">;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  readOnly?: boolean;
  onChanged?: () => void;
}

export function HoldingsTable({
  positions, livePrices, flashes, selectedSymbol, onSelectSymbol, readOnly = false, onChanged,
}: HoldingsTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ quantity: "", avg_cost_price: "" });

  const etfs = positions.filter((p) => ETF_TYPES.has(p.asset_type));
  const stocks = positions.filter((p) => !ETF_TYPES.has(p.asset_type));

  const handleUpdate = async (id: string) => {
    await api.updatePosition(id, {
      quantity: editForm.quantity ? parseFloat(editForm.quantity) : undefined,
      avg_cost_price: editForm.avg_cost_price ? parseFloat(editForm.avg_cost_price) : undefined,
    });
    setEditingId(null);
    onChanged?.();
  };
  const handleDelete = async (id: string) => {
    await api.deletePosition(id);
    onChanged?.();
  };

  const renderRow = (pos: Position) => {
    const live = livePrices[pos.symbol];
    const livePrice = live?.price ?? pos.last_price ?? 0;
    const livePnlPct = pos.avg_cost_price ? (livePrice / pos.avg_cost_price - 1) * 100 : pos.pnl_pct;
    const flash = flashes[pos.symbol];
    const hasSparkline = pos.sparkline && pos.sparkline.length >= 2;

    if (editingId === pos.id) {
      return (
        <div key={pos.id} className="flex items-center gap-2 p-3 rounded-[14px] bg-muted flex-wrap">
          <span className="font-bold text-[14px] w-14">{pos.symbol}</span>
          <Input value={editForm.quantity} onChange={(e) => setEditForm({ ...editForm, quantity: e.target.value })} className="h-8 w-16 text-[13px] rounded-[14px]" placeholder="Qty" />
          <Input value={editForm.avg_cost_price} onChange={(e) => setEditForm({ ...editForm, avg_cost_price: e.target.value })} className="h-8 w-20 text-[13px] rounded-[14px]" placeholder="Price" />
          <button onClick={() => handleUpdate(pos.id)} className="cursor-pointer"><Check className="h-4 w-4 text-gain" /></button>
          <button onClick={() => setEditingId(null)} className="cursor-pointer"><X className="h-4 w-4 text-muted-foreground" /></button>
        </div>
      );
    }

    return (
      <div
        key={pos.id}
        className={cn(
          ROW_GRID,
          "items-center px-3.5 py-3 pr-4 rounded-[14px] cursor-pointer transition-all duration-200 group hover:bg-accent",
          selectedSymbol === pos.symbol && "bg-accent",
          flash === "up" && "flash-up",
          flash === "down" && "flash-down",
        )}
        onClick={() => onSelectSymbol(pos.symbol)}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-1">
            <p className="font-bold text-[14px] truncate">{pos.symbol}</p>
            {pos.manual_price ? (
              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground font-medium shrink-0">manual price</span>
            ) : (
              pos.price_stale && <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0" />
            )}
          </div>
          <p className="text-[11px] text-muted-foreground truncate">{pos.name}</p>
        </div>
        <div className="hidden lg:flex items-center justify-center">
          {hasSparkline ? (
            <Sparkline data={pos.sparkline} color={livePnlPct >= 0 ? "#3b82f6" : "#ff3b30"} width={80} height={32} />
          ) : (
            <div className="w-20 h-8 flex items-center justify-center" aria-hidden>
              <span className="block w-8 h-px bg-muted-foreground/25" />
            </div>
          )}
        </div>
        <div className="text-right">
          <p className="font-mono tabular-nums text-[13px] font-semibold">{pos.quantity}</p>
          <p className="text-[10px] text-muted-foreground">shares</p>
        </div>
        <div className="text-right">
          <p className="font-mono tabular-nums text-[13px] font-semibold">{livePrice.toFixed(2)}<span className="text-[11px] text-muted-foreground ml-1">{pos.currency}</span></p>
          <p className="font-mono tabular-nums text-[11px] text-muted-foreground">cost {pos.avg_cost_price.toFixed(2)}</p>
        </div>
        <div className="flex items-center justify-end gap-2">
          <div className="text-right hidden sm:block">
            {pos.fx_unavailable ? (
              <p className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">FX N/A</p>
            ) : (
              <>
                <p className="font-mono tabular-nums text-[13px] font-semibold">{formatCurrency(pos.market_value)}</p>
                <p className={`font-mono tabular-nums text-[11px] font-semibold ${livePnlPct >= 0 ? "text-gain" : "text-loss"}`}>{livePnlPct >= 0 ? "+" : ""}{livePnlPct.toFixed(1)}%</p>
                <p className={`text-[11px] tabular-nums ${pos.unrealized_pnl >= 0 ? "text-gain" : "text-loss"}`}>{pos.unrealized_pnl >= 0 ? "+" : ""}{formatCurrency(pos.unrealized_pnl)}</p>
              </>
            )}
            <p className="text-[10px] text-muted-foreground mt-0.5">{pos.weight_pct.toFixed(1)}% of portfolio</p>
          </div>
          {!readOnly && (
            <div className="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
              <button className="cursor-pointer p-1 rounded-lg hover:bg-background" onClick={() => { setEditingId(pos.id); setEditForm({ quantity: String(pos.quantity), avg_cost_price: String(pos.avg_cost_price) }); }}><Pencil className="h-3.5 w-3.5 text-muted-foreground" /></button>
              <button className="cursor-pointer p-1 rounded-lg hover:bg-background" onClick={() => handleDelete(pos.id)}><Trash2 className="h-3.5 w-3.5 text-muted-foreground" /></button>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <GlassCard delay={0.25} className="md:col-span-1 lg:col-span-2 !p-4">
      <div className="space-y-4 max-h-[460px] overflow-y-auto pr-1" style={{ scrollbarGutter: "stable" }}>
        <section>
          <p className="text-[13px] font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Stocks {stocks.length > 0 && `(${stocks.length})`}</p>
          {stocks.length === 0 ? (
            <p className="text-[12px] text-muted-foreground py-3">No individual stock holdings.</p>
          ) : (
            <div className="space-y-1">{stocks.map(renderRow)}</div>
          )}
        </section>
        <section>
          <p className="text-[13px] font-semibold text-muted-foreground mb-2 uppercase tracking-wide">ETFs {etfs.length > 0 && `(${etfs.length})`}</p>
          {etfs.length === 0 ? (
            <p className="text-[12px] text-muted-foreground py-3">No ETF holdings.</p>
          ) : (
            <div className="space-y-1">{etfs.map(renderRow)}</div>
          )}
        </section>
      </div>
    </GlassCard>
  );
}
