"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowDown, ArrowUp, Eye, EyeOff, LayoutGrid, RotateCcw, X } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { cn } from "@/lib/format";
import { useDashboardLayout } from "./use-dashboard-layout";
import { WIDGET_BY_ID } from "./widget-registry";

/** "Edit layout" toggle + the panel it opens: show/hide each widget and
 * reorder with up/down buttons (no drag-and-drop dependency). Persists via
 * useDashboardLayout — every other consumer of that hook (the dashboard
 * grid itself) re-renders automatically through the shared query cache. */
export function EditLayoutBar() {
  const [editing, setEditing] = useState(false);
  const { layout, saving, toggleVisible, moveUp, moveDown, resetToDefault } = useDashboardLayout();

  return (
    <div>
      <div className="flex items-center justify-end">
        <button
          onClick={() => setEditing((v) => !v)}
          className={cn(
            "flex items-center gap-2 rounded-xl border border-border px-4 h-10 text-[14px] font-medium",
            "hover:bg-accent active:scale-[0.98] cursor-pointer transition-all",
            editing && "bg-accent",
          )}
        >
          {editing ? <X className="h-4 w-4" /> : <LayoutGrid className="h-4 w-4" />}
          {editing ? "Done" : "Edit layout"}
        </button>
      </div>

      <AnimatePresence>
        {editing && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <GlassCard className="mt-3 space-y-1">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[13px] text-muted-foreground">Show, hide, and reorder dashboard widgets.</p>
                <button
                  onClick={() => resetToDefault()}
                  disabled={saving}
                  className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground cursor-pointer disabled:opacity-50"
                >
                  <RotateCcw className="h-3 w-3" />
                  Reset to default
                </button>
              </div>
              {layout.map((item, i) => {
                const widget = WIDGET_BY_ID[item.id];
                if (!widget) return null;
                return (
                  <div key={item.id} className="flex items-center justify-between py-2 px-1 rounded-lg hover:bg-accent/50">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleVisible(item.id)}
                        disabled={saving}
                        className="rounded-lg p-1.5 hover:bg-accent cursor-pointer transition-all disabled:opacity-50"
                        title={item.visible ? "Hide" : "Show"}
                      >
                        {item.visible ? <Eye className="h-4 w-4 text-foreground" /> : <EyeOff className="h-4 w-4 text-muted-foreground" />}
                      </button>
                      <span className={cn("text-[14px]", !item.visible && "text-muted-foreground")}>{widget.label}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button
                        onClick={() => moveUp(item.id)}
                        disabled={saving || i === 0}
                        className="rounded-lg p-1.5 hover:bg-accent cursor-pointer transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => moveDown(item.id)}
                        disabled={saving || i === layout.length - 1}
                        className="rounded-lg p-1.5 hover:bg-accent cursor-pointer transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
