"use client";

import { useMemo, useState } from "react";
import { CalendarClock, Check, Loader2, Sparkles, Trash2, X } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { formatCurrency, formatDate, cn } from "@/lib/format";
import {
  useRecurringQuery, useRecurringDetectedQuery, useSettingsQuery, useUpdateSettings,
  useCreateRecurring, useDeleteRecurring,
} from "@/hooks/queries";

const WINDOW_DAYS = 30;
const SETTINGS_KEY = "dismissed_recurring_suggestions";

function normalizeMerchant(name: string): string {
  return name.trim().toLowerCase();
}

function withinWindow(iso: string): boolean {
  const due = new Date(iso).getTime();
  const now = Date.now();
  const horizon = now + WINDOW_DAYS * 24 * 60 * 60 * 1000;
  return due <= horizon;
}

interface UpcomingItem {
  key: string;
  name: string;
  amount: number;
  currency: string;
  frequency: string;
  next_due_date: string;
  suggested: boolean;
  recurringId?: string;
}

/** Bills due in the next 30 days — both tracked RecurringExpenses and
 * auto-detected suggestions inferred from transaction history. Suggestions
 * can be accepted (creates a tracked RecurringExpense) or dismissed
 * (remembered in user settings so they aren't re-suggested). */
export function UpcomingPaymentsWidget() {
  const recurringQuery = useRecurringQuery();
  const detectedQuery = useRecurringDetectedQuery();
  const settingsQuery = useSettingsQuery();
  const updateSettings = useUpdateSettings();
  const createRecurring = useCreateRecurring();
  const deleteRecurring = useDeleteRecurring();

  const [busyKey, setBusyKey] = useState<string | null>(null);

  const dismissed: string[] = useMemo(() => {
    const raw = settingsQuery.data?.settings?.[SETTINGS_KEY];
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }, [settingsQuery.data]);

  const items: UpcomingItem[] = useMemo(() => {
    const tracked: UpcomingItem[] = (recurringQuery.data ?? [])
      .filter((r) => r.active && withinWindow(r.next_due_date))
      .map((r) => ({
        key: `tracked:${r.id}`,
        name: r.name,
        amount: r.amount,
        currency: r.currency,
        frequency: r.frequency,
        next_due_date: r.next_due_date,
        suggested: false,
        recurringId: r.id,
      }));

    const trackedMerchants = new Set((recurringQuery.data ?? []).map((r) => normalizeMerchant(r.name)));

    const suggested: UpcomingItem[] = (detectedQuery.data ?? [])
      .filter((s) => withinWindow(s.next_due_date))
      .filter((s) => !dismissed.includes(normalizeMerchant(s.merchant)))
      .filter((s) => !trackedMerchants.has(normalizeMerchant(s.merchant)))
      .map((s) => ({
        key: `suggested:${normalizeMerchant(s.merchant)}`,
        name: s.merchant,
        amount: s.amount,
        currency: s.currency,
        frequency: s.frequency,
        next_due_date: s.next_due_date,
        suggested: true,
      }));

    return [...tracked, ...suggested].sort((a, b) => a.next_due_date.localeCompare(b.next_due_date));
  }, [recurringQuery.data, detectedQuery.data, dismissed]);

  const accept = async (item: UpcomingItem) => {
    setBusyKey(item.key);
    try {
      await createRecurring.mutateAsync({
        name: item.name, amount: item.amount, currency: item.currency,
        frequency: item.frequency, next_due_date: item.next_due_date,
      });
    } finally {
      setBusyKey(null);
    }
  };

  const dismiss = async (item: UpcomingItem) => {
    setBusyKey(item.key);
    try {
      const next = Array.from(new Set([...dismissed, normalizeMerchant(item.name)]));
      await updateSettings.mutateAsync({ [SETTINGS_KEY]: JSON.stringify(next) });
    } finally {
      setBusyKey(null);
    }
  };

  const removeTracked = async (item: UpcomingItem) => {
    if (!item.recurringId) return;
    if (!confirm(`Stop tracking "${item.name}" as a recurring expense?`)) return;
    setBusyKey(item.key);
    try {
      await deleteRecurring.mutateAsync(item.recurringId);
    } finally {
      setBusyKey(null);
    }
  };

  const loading = recurringQuery.isLoading || detectedQuery.isLoading;

  return (
    <GlassCard>
      <h2 className="text-[16px] font-semibold mb-5">Upcoming Payments</h2>
      {loading ? (
        <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : items.length === 0 ? (
        <div className="text-center py-12">
          <CalendarClock className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" strokeWidth={1.2} />
          <p className="text-muted-foreground">Nothing due in the next {WINDOW_DAYS} days</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.key}
              className={cn(
                "flex items-center justify-between py-2 px-3 rounded-xl",
                item.suggested && "bg-primary/5 ring-1 ring-primary/15",
              )}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={cn("h-9 w-9 rounded-xl flex items-center justify-center shrink-0", item.suggested ? "bg-primary/10" : "bg-muted")}>
                  {item.suggested ? <Sparkles className="h-4 w-4 text-primary" /> : <CalendarClock className="h-4 w-4 text-muted-foreground" />}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-[14px] font-medium truncate">{item.name}</p>
                    {item.suggested && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-primary/15 text-primary uppercase tracking-wide shrink-0">Suggested</span>
                    )}
                  </div>
                  <p className="text-[12px] text-muted-foreground capitalize">{item.frequency} · due {formatDate(item.next_due_date)}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <p className="font-mono tabular-nums text-[14px] font-semibold">{formatCurrency(item.amount, item.currency)}</p>
                {item.suggested ? (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => accept(item)}
                      disabled={busyKey === item.key}
                      title="Accept — track as a recurring expense"
                      className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-gain"
                    >
                      {busyKey === item.key ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    </button>
                    <button
                      onClick={() => dismiss(item)}
                      disabled={busyKey === item.key}
                      title="Dismiss — don't suggest again"
                      className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => removeTracked(item)}
                    disabled={busyKey === item.key}
                    className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground hover:text-loss"
                  >
                    {busyKey === item.key ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
