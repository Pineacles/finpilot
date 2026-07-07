"use client";

import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { LineChart } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const RANGES = [
  { value: "1d", label: "1D" }, { value: "5d", label: "1W" }, { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" }, { value: "6mo", label: "6M" }, { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" }, { value: "5y", label: "5Y" },
];

interface SymbolChartDialogProps {
  symbol: string | null;
  onClose: () => void;
  fetchChart: (ticker: string, range: string) => Promise<{ date: string; close: number }[]>;
}

// Lightweight chart-in-a-modal for viewing a symbol from the transaction
// history table without disturbing the main holdings chart panel's state.
export function SymbolChartDialog({ symbol, onClose, fetchChart }: SymbolChartDialogProps) {
  const [range, setRange] = useState("1y");
  const [data, setData] = useState<{ date: string; close: number }[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setLoading(true);
    fetchChart(symbol, range)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setData([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, range, fetchChart]);

  return (
    <Dialog open={symbol !== null} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="rounded-3xl max-w-2xl">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><LineChart className="h-5 w-5 text-primary" />{symbol} — Price Chart</DialogTitle></DialogHeader>
        <div className="flex gap-1 mb-3">
          {RANGES.map((r) => (
            <button key={r.value} onClick={() => setRange(r.value)} className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-all cursor-pointer ${range === r.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"}`}>{r.label}</button>
          ))}
        </div>
        <div className="h-64">
          {loading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">Loading...</div>
          ) : data.length === 0 ? (
            <p className="text-[13px] text-muted-foreground text-center py-8">No data available</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="symbol-chart-dialog-gradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} stroke="var(--muted-foreground)" />
                <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} stroke="var(--muted-foreground)" />
                <Tooltip formatter={(v: any) => Number(v).toFixed(2)} />
                <Area type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} fill="url(#symbol-chart-dialog-gradient)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
