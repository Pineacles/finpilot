"use client";

import { useEffect, useState } from "react";
import { api, Budget, Category } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { GlassCard } from "@/components/glass-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, Trash2, X } from "lucide-react";

export default function BudgetsPage() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", amount: "", category_id: "", period: "monthly" });

  const load = () => {
    Promise.all([api.budgets(), api.categories()])
      .then(([b, c]) => { setBudgets(b); setCategories(c); })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleCreate = async () => {
    await api.createBudget({
      name: form.name,
      amount: parseFloat(form.amount),
      category_id: form.category_id || undefined,
      period: form.period,
      start_date: new Date().toISOString().slice(0, 10),
    });
    setForm({ name: "", amount: "", category_id: "", period: "monthly" });
    setOpen(false);
    load();
  };

  const handleDelete = async (id: string) => {
    await api.deleteBudget(id);
    load();
  };

  const totalBudget = budgets.reduce((s, b) => s + b.amount, 0);
  const totalSpent = budgets.reduce((s, b) => s + b.spent, 0);
  const overall = totalBudget > 0 ? (totalSpent / totalBudget) * 100 : 0;
  const circumference = 2 * Math.PI * 75;

  return (
    <div className="space-y-6 p-1">
      {/* Budget summary + action */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono tabular-nums">{formatCurrency(totalSpent)}</span>
          {" of "}
          <span className="font-mono tabular-nums">{formatCurrency(totalBudget)}</span>
          {" · "}{overall.toFixed(0)}% of monthly budget used
        </p>
        <button
          onClick={() => setOpen(true)}
          className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-semibold cursor-pointer shadow-[0_10px_24px_-10px_var(--color-primary)] hover:opacity-90 transition-opacity"
        >
          <Plus className="h-4 w-4" />
          New Budget
        </button>
      </div>

      {/* Ring gauge overview */}
      {!loading && budgets.length > 0 && (
        <GlassCard delay={0.05} className="grid grid-cols-[180px_1fr] gap-8 items-center">
          <div className="relative w-[180px] h-[180px]">
            <svg width={180} height={180} style={{ transform: "rotate(-90deg)" }}>
              <circle cx={90} cy={90} r={75} fill="none" stroke="var(--color-accent)" strokeWidth={18} />
              <circle
                cx={90} cy={90} r={75} fill="none"
                stroke={overall > 100 ? "var(--color-loss)" : "var(--color-primary)"}
                strokeWidth={18} strokeLinecap="round"
                strokeDasharray={`${Math.min(overall, 100) / 100 * circumference} ${circumference}`}
                style={{ transition: "stroke-dasharray 900ms cubic-bezier(0.25,0.46,0.45,0.94)" }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="font-mono text-3xl font-extrabold tabular-nums tracking-tight">{overall.toFixed(0)}%</span>
              <span className="text-[11px] text-muted-foreground uppercase tracking-wider mt-0.5">Used</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-5">
            <div>
              <p className="text-xs text-muted-foreground mb-1.5">Total Budget</p>
              <p className="font-mono text-xl font-bold tabular-nums">{formatCurrency(totalBudget)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1.5">Spent</p>
              <p className="font-mono text-xl font-bold tabular-nums text-loss">{formatCurrency(totalSpent)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1.5">Remaining</p>
              <p className="font-mono text-xl font-bold tabular-nums text-gain">{formatCurrency(Math.max(0, totalBudget - totalSpent))}</p>
            </div>
          </div>
        </GlassCard>
      )}

      {/* Budget cards */}
      {loading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : budgets.length === 0 ? (
        <GlassCard delay={0.05}>
          <div className="py-12 text-center text-muted-foreground">
            <p className="text-sm">No budgets yet. Create your first budget to start tracking spending.</p>
          </div>
        </GlassCard>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {budgets.map((b, i) => {
            const pct = b.pct_used;
            const over = pct > 100;
            const catColor = "#6b7280";
            return (
              <GlassCard key={b.id} delay={i * 0.04 + 0.1} className="flex flex-col gap-3.5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-2 h-2 rounded-sm" style={{ background: catColor }} />
                      <span className="text-[15px] font-semibold">{b.name}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground capitalize">
                      {b.period}{b.category_name ? ` · ${b.category_name}` : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDelete(b.id)}
                    className="w-8 h-8 rounded-[10px] flex items-center justify-center text-muted-foreground hover:bg-accent transition-colors cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div>
                  <div className="flex items-baseline justify-between mb-2">
                    <span className={`font-mono text-xl font-bold tabular-nums ${over ? "text-loss" : ""}`}>
                      {formatCurrency(b.spent)}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground tabular-nums">
                      of {formatCurrency(b.amount)}
                    </span>
                  </div>
                  <div className="h-2.5 rounded-full bg-accent overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.min(pct, 100)}%`,
                        background: over
                          ? "linear-gradient(90deg, #ef4444, #f97316)"
                          : `linear-gradient(90deg, ${catColor}, ${catColor}bb)`,
                      }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {over
                      ? <span className="text-loss font-semibold">Over by {formatCurrency(b.spent - b.amount)}</span>
                      : <span>{formatCurrency(b.remaining)} remaining</span>
                    }
                  </p>
                </div>
              </GlassCard>
            );
          })}

          {/* Add new card */}
          <button
            onClick={() => setOpen(true)}
            className="glass bg-card rounded-[20px] p-6 min-h-[180px] flex flex-col items-center justify-center gap-2.5 border-2 border-dashed border-border text-muted-foreground hover:bg-accent hover:text-foreground transition-all duration-150 cursor-pointer"
          >
            <div className="w-12 h-12 rounded-[14px] bg-accent flex items-center justify-center">
              <Plus className="h-5 w-5" />
            </div>
            <span className="text-sm font-medium">Add new budget</span>
          </button>
        </div>
      )}

      {/* Create Modal */}
      {open && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setOpen(false)}
        >
          <div
            className="glass bg-card rounded-3xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold">Create Budget</h2>
              <button
                onClick={() => setOpen(false)}
                className="w-8 h-8 rounded-[10px] bg-accent flex items-center justify-center text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Name</Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Groceries"
                  className="h-11 rounded-xl bg-accent border-0"
                />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Amount (CHF)</Label>
                <Input
                  type="number"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  placeholder="500"
                  className="h-11 rounded-xl bg-accent border-0"
                />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Category (optional)</Label>
                <select
                  className="w-full h-11 rounded-xl bg-accent px-3 text-[14px] border-0"
                  value={form.category_id}
                  onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                >
                  <option value="">All categories</option>
                  {categories.filter((c) => c.type === "expense").map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Period</Label>
                <div className="flex gap-1.5">
                  {["weekly", "monthly", "yearly"].map((p) => (
                    <button
                      key={p}
                      onClick={() => setForm({ ...form, period: p })}
                      className={`flex-1 h-10 rounded-[10px] text-[12px] font-semibold capitalize cursor-pointer transition-all ${
                        form.period === p
                          ? "bg-primary text-primary-foreground"
                          : "bg-accent text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <button
                onClick={handleCreate}
                className="w-full h-11 rounded-xl bg-primary text-primary-foreground text-sm font-semibold cursor-pointer shadow-[0_10px_24px_-10px_var(--color-primary)] hover:opacity-90 transition-opacity mt-1"
              >
                Create Budget
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
