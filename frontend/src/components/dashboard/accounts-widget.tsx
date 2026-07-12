"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Landmark, CreditCard, Pencil, Loader2 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { useOverviewQuery, queryKeys } from "@/hooks/queries";

/** Bank + credit card accounts with balances. Balances can be fixed inline,
 * since the "gateway for the user's AI agent" principle applies to humans too:
 * easy to see and easy to correct. */
export function AccountsWidget() {
  const { data, isLoading } = useOverviewQuery();
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  const accounts = data?.accounts ?? [];

  const startEdit = (id: string, current: number) => {
    setEditingId(id);
    setEditValue(String(Math.round(current * 100) / 100));
  };

  const save = async () => {
    if (!editingId || !editValue) return;
    setSaving(true);
    try {
      await api.setAccountBalance(editingId, parseFloat(editValue));
      await queryClient.invalidateQueries({ queryKey: queryKeys.overview() });
      setEditingId(null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <GlassCard>
      <h2 className="text-[16px] font-semibold mb-5">Accounts</h2>
      {isLoading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : accounts.length === 0 ? (
        <p className="text-[13px] text-muted-foreground py-4">No accounts yet.</p>
      ) : (
        <div className="space-y-3">
          {accounts.map((a) => {
            const isCc = a.type === "credit_card";
            return (
              <div key={a.id} className="flex items-center justify-between py-1">
                <div className="flex items-center gap-3">
                  <div className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 ${isCc ? "bg-rose-100 dark:bg-rose-500/15" : "bg-blue-100 dark:bg-blue-500/15"}`}>
                    {isCc ? <CreditCard className="h-4 w-4 text-rose-600 dark:text-rose-400" /> : <Landmark className="h-4 w-4 text-blue-600 dark:text-blue-400" />}
                  </div>
                  <div>
                    <p className="text-[14px] font-medium">{a.name}</p>
                    <p className="text-[12px] text-muted-foreground capitalize">{a.type.replace("_", " ")}</p>
                  </div>
                </div>

                {editingId === a.id ? (
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="w-24 h-8 rounded-lg bg-accent px-2 text-[13px] outline-none focus:ring-2 focus:ring-primary/30 tabular-nums"
                      autoFocus
                    />
                    <button onClick={save} disabled={saving} className="text-[12px] font-medium text-primary cursor-pointer disabled:opacity-50">
                      {saving ? "..." : "Save"}
                    </button>
                    <button onClick={() => setEditingId(null)} className="text-[12px] text-muted-foreground cursor-pointer">Cancel</button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <p className={`font-mono tabular-nums text-[14px] font-semibold ${isCc && a.balance < 0 ? "text-loss" : ""}`}>
                      {formatCurrency(a.balance, a.currency)}
                    </p>
                    <button onClick={() => startEdit(a.id, a.balance)} className="p-1 rounded-lg hover:bg-accent cursor-pointer transition-colors">
                      <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}
