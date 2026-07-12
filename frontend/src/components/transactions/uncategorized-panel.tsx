"use client";

import { useState } from "react";
import { AlertCircle, ListChecks, Loader2, Sparkles, Tag } from "lucide-react";
import { api, Category, TransactionItem } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/format";
import { GlassCard } from "@/components/glass-card";
import { groupCategories, CategoryGroup } from "@/lib/categories";

interface UncategorizedPanelProps {
  uncategorized: TransactionItem[];
  categories: Category[];
  onDone: () => void | Promise<void>;
}

/** Bulk-categorization panel for transactions with no category: manual bulk
 * apply or AI-assisted categorization. Shown above the main table only when
 * there's something to categorize. */
export function UncategorizedPanel({ uncategorized, categories, onDone }: UncategorizedPanelProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkCategoryId, setBulkCategoryId] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  const groupedCategories: CategoryGroup[] = groupCategories(categories);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(selected.size === uncategorized.length ? new Set() : new Set(uncategorized.map((t) => t.id)));
  };

  const handleBulkCategorize = async () => {
    if (!bulkCategoryId || selected.size === 0) return;
    setBulkLoading(true);
    try {
      await api.bulkManualCategorize(Array.from(selected), bulkCategoryId);
      setSelected(new Set());
      setBulkCategoryId("");
      await onDone();
    } finally {
      setBulkLoading(false);
    }
  };

  const handleAiCategorize = async () => {
    const ids = selected.size > 0 ? Array.from(selected) : uncategorized.map((t) => t.id);
    if (ids.length === 0) return;
    setAiLoading(true);
    try {
      await api.aiCategorize(ids);
      setSelected(new Set());
      await onDone();
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <GlassCard className="border-l-4 border-l-primary !rounded-[14px] bg-primary/5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center h-8 w-8 rounded-xl bg-amber-500/10">
            <AlertCircle className="h-4 w-4 text-amber-500" />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold">Uncategorized</h3>
            <p className="text-[13px] text-muted-foreground">
              {uncategorized.length} transaction{uncategorized.length !== 1 ? "s" : ""} need categorization
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={toggleAll}
            className={cn(
              "flex items-center gap-1.5 rounded-xl px-3 h-9 text-[13px] font-medium",
              "bg-accent hover:bg-accent/80 active:scale-[0.98] cursor-pointer transition-all",
            )}
          >
            <ListChecks className="h-3.5 w-3.5" />
            {selected.size === uncategorized.length ? "Deselect All" : "Select All"}
          </button>

          <select
            value={bulkCategoryId}
            onChange={(e) => setBulkCategoryId(e.target.value)}
            className="h-9 rounded-xl bg-accent px-3 text-[13px] border-none outline-none cursor-pointer"
          >
            <option value="">Category...</option>
            {groupedCategories.map((g) => (
              <optgroup key={g.id} label={g.name}>
                {g.children.length > 0 ? (
                  g.children.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)
                ) : (
                  <option value={g.id}>{g.name}</option>
                )}
              </optgroup>
            ))}
          </select>

          <button
            onClick={handleBulkCategorize}
            disabled={!bulkCategoryId || selected.size === 0 || bulkLoading}
            className={cn(
              "flex items-center gap-1.5 rounded-xl px-3 h-9 text-[13px] font-medium",
              "bg-primary text-primary-foreground active:scale-[0.98] cursor-pointer transition-all",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            {bulkLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Tag className="h-3.5 w-3.5" />}
            Apply
          </button>

          <button
            onClick={handleAiCategorize}
            disabled={aiLoading}
            className={cn(
              "flex items-center gap-1.5 rounded-xl px-4 h-9 text-[13px] font-medium",
              "bg-chart-2 text-white active:scale-[0.98] cursor-pointer transition-all",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {aiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            AI Categorize{selected.size > 0 ? ` (${selected.size})` : ` (${uncategorized.length})`}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto">
        {uncategorized.slice(0, 20).map((txn) => (
          <button
            key={txn.id}
            onClick={() => toggle(txn.id)}
            className={cn(
              "flex items-center gap-2 rounded-xl px-3 py-1.5 text-[13px] transition-all cursor-pointer",
              "active:scale-[0.98]",
              selected.has(txn.id) ? "bg-primary/15 text-primary ring-1 ring-primary/30" : "bg-accent hover:bg-accent/80",
            )}
          >
            <span className="truncate max-w-[140px]">{txn.merchant}</span>
            <span className={cn("font-medium tabular-nums", txn.amount >= 0 ? "text-gain" : "text-loss")}>
              {formatCurrency(txn.amount, txn.currency)}
            </span>
          </button>
        ))}
        {uncategorized.length > 20 && (
          <span className="text-[13px] text-muted-foreground self-center ml-1">+{uncategorized.length - 20} more</span>
        )}
      </div>
    </GlassCard>
  );
}
