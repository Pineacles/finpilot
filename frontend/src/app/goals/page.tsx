"use client";

import { useEffect, useState } from "react";
import { api, SavingsGoal, Milestone } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { GlassCard } from "@/components/glass-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, Target, Flag, CheckCircle2, X } from "lucide-react";

const GOAL_COLORS = ["#3b82f6", "#8b5cf6", "#22c55e", "#f59e0b", "#ec4899", "#14b8a6"];

export default function GoalsPage() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"goals" | "milestones">("goals");
  const [goalOpen, setGoalOpen] = useState(false);
  const [msOpen, setMsOpen] = useState(false);
  const [goalForm, setGoalForm] = useState({ name: "", target_amount: "", target_date: "" });
  const [msForm, setMsForm] = useState({ name: "", description: "", target_date: "", target_net_worth: "" });

  const load = () => {
    Promise.all([api.goals(), api.milestones()])
      .then(([g, m]) => { setGoals(g); setMilestones(m); })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const createGoal = async () => {
    await api.createGoal({
      name: goalForm.name,
      target_amount: parseFloat(goalForm.target_amount),
      target_date: goalForm.target_date || undefined,
    });
    setGoalForm({ name: "", target_amount: "", target_date: "" });
    setGoalOpen(false);
    load();
  };

  const createMilestone = async () => {
    await api.createMilestone({
      name: msForm.name,
      description: msForm.description || undefined,
      target_date: msForm.target_date || undefined,
      target_net_worth: msForm.target_net_worth ? parseFloat(msForm.target_net_worth) : undefined,
    });
    setMsForm({ name: "", description: "", target_date: "", target_net_worth: "" });
    setMsOpen(false);
    load();
  };

  return (
    <div className="space-y-6 p-1">
      {/* Action bar */}
      <div className="flex items-center justify-end">
        <button
          onClick={() => tab === "goals" ? setGoalOpen(true) : setMsOpen(true)}
          className="flex items-center gap-2 px-5 py-3 rounded-xl bg-primary text-primary-foreground text-[14px] font-semibold cursor-pointer shadow-[0_10px_24px_-10px_rgba(59,130,246,0.4)] hover:opacity-90 transition-opacity"
        >
          <Plus className="h-4 w-4" />
          {tab === "goals" ? "New Goal" : "New Milestone"}
        </button>
      </div>

      {/* Tabs */}
      <div className="glass bg-card rounded-[14px] p-1.5 inline-flex gap-1 self-start">
        {([
          { id: "goals" as const, label: "Savings Goals", Icon: Target },
          { id: "milestones" as const, label: "Milestones", Icon: Flag },
        ]).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-[10px] text-[13px] font-semibold transition-all cursor-pointer ${
              tab === t.id
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <t.Icon className="h-3.5 w-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Goals tab */}
      {tab === "goals" && (
        loading ? (
          <p className="text-[13px] text-muted-foreground">Loading…</p>
        ) : goals.length === 0 ? (
          <GlassCard delay={0.05}>
            <div className="py-12 text-center text-muted-foreground">
              <Target className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-[13px]">No savings goals yet. Create your first goal!</p>
            </div>
          </GlassCard>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {goals.map((g, i) => {
              const color = GOAL_COLORS[i % GOAL_COLORS.length];
              const complete = g.progress_pct >= 100;
              return (
                <GlassCard key={g.id} delay={i * 0.05 + 0.1} className="flex flex-col gap-4 relative overflow-hidden">
                  {/* Blurred glow orb */}
                  <div
                    className="absolute -top-16 -right-16 w-48 h-48 rounded-full pointer-events-none"
                    style={{ background: color, filter: "blur(50px)", opacity: 0.15 }}
                  />
                  <div className="flex items-start justify-between relative z-10">
                    <div
                      className="w-11 h-11 rounded-[14px] flex items-center justify-center text-white shrink-0"
                      style={{ background: color }}
                    >
                      <Target className="h-5 w-5" />
                    </div>
                    {complete && (
                      <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-gain px-2.5 py-1 rounded-[10px] bg-gain/10">
                        <CheckCircle2 className="h-3 w-3" />
                        Achieved
                      </span>
                    )}
                  </div>
                  <div className="relative z-10">
                    <p className="text-[17px] font-bold">{g.name}</p>
                    {g.target_date && (
                      <p className="text-xs text-muted-foreground mt-0.5">Target: {formatDate(g.target_date)}</p>
                    )}
                  </div>
                  <div className="relative z-10">
                    <div className="flex items-baseline justify-between mb-2">
                      <span className="font-mono tabular-nums text-[20px] font-bold">{formatCurrency(g.current_amount)}</span>
                      <span className="font-mono tabular-nums text-[11px] text-muted-foreground">of {formatCurrency(g.target_amount)}</span>
                    </div>
                    <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${Math.min(g.progress_pct, 100)}%`,
                          background: `linear-gradient(90deg, ${color}, ${color}aa)`,
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                      <span>{g.progress_pct.toFixed(1)}% complete</span>
                      <span>{formatCurrency(Math.max(0, g.target_amount - g.current_amount))} to go</span>
                    </div>
                  </div>
                </GlassCard>
              );
            })}
          </div>
        )
      )}

      {/* Milestones tab */}
      {tab === "milestones" && (
        loading ? (
          <p className="text-[13px] text-muted-foreground">Loading…</p>
        ) : milestones.length === 0 ? (
          <GlassCard delay={0.05}>
            <div className="py-12 text-center text-muted-foreground">
              <Flag className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-[13px]">No milestones yet. Create your first milestone!</p>
            </div>
          </GlassCard>
        ) : (
          <GlassCard delay={0.1} className="relative">
            <div className="absolute left-[22px] top-10 bottom-10 w-0.5 bg-border" />
            <div className="space-y-0 divide-y divide-border">
              {milestones.map((m) => (
                <div key={m.id} className="grid grid-cols-[40px_1fr_140px_120px] gap-4 py-4 items-center">
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center border-2 z-10 ${
                      m.achieved
                        ? "bg-gain/10 text-gain border-gain"
                        : "bg-muted text-muted-foreground border-border"
                    }`}
                  >
                    {m.achieved ? <CheckCircle2 className="h-4 w-4" /> : <Flag className="h-4 w-4" />}
                  </div>
                  <div>
                    <p className="text-[15px] font-semibold">{m.name}</p>
                    {m.description && <p className="text-xs text-muted-foreground mt-0.5">{m.description}</p>}
                  </div>
                  <div>
                    {m.target_date && (
                      <>
                        <p className="text-[11px] text-muted-foreground mb-0.5">Target date</p>
                        <p className="text-[13px] font-medium">{formatDate(m.target_date)}</p>
                      </>
                    )}
                  </div>
                  <div className="text-right">
                    {m.target_net_worth && (
                      <>
                        <p className="text-[11px] text-muted-foreground mb-0.5">Target</p>
                        <p className="font-mono tabular-nums text-[13px] font-semibold">{formatCurrency(m.target_net_worth)}</p>
                      </>
                    )}
                    {m.achieved && (
                      <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-lg bg-gain/10 text-gain mt-1 inline-block">
                        Achieved
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        )
      )}

      {/* Create Goal Modal */}
      {goalOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setGoalOpen(false)}
        >
          <div
            className="glass bg-card rounded-3xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[16px] font-bold">Create Savings Goal</h2>
              <button
                onClick={() => setGoalOpen(false)}
                className="w-8 h-8 rounded-[10px] bg-muted flex items-center justify-center cursor-pointer hover:bg-muted/80 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Name</Label>
                <Input value={goalForm.name} onChange={(e) => setGoalForm({ ...goalForm, name: e.target.value })} placeholder="e.g. Emergency Fund" className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Target Amount (CHF)</Label>
                <Input type="number" value={goalForm.target_amount} onChange={(e) => setGoalForm({ ...goalForm, target_amount: e.target.value })} placeholder="10000" className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Target Date (optional)</Label>
                <Input type="date" value={goalForm.target_date} onChange={(e) => setGoalForm({ ...goalForm, target_date: e.target.value })} className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <button
                onClick={createGoal}
                className="w-full h-11 rounded-xl bg-primary text-primary-foreground text-[14px] font-semibold cursor-pointer shadow-[0_10px_24px_-10px_rgba(59,130,246,0.4)] hover:opacity-90 transition-opacity mt-1"
              >
                Create Goal
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Milestone Modal */}
      {msOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setMsOpen(false)}
        >
          <div
            className="glass bg-card rounded-3xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[16px] font-bold">Create Milestone</h2>
              <button
                onClick={() => setMsOpen(false)}
                className="w-8 h-8 rounded-[10px] bg-muted flex items-center justify-center cursor-pointer hover:bg-muted/80 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Name</Label>
                <Input value={msForm.name} onChange={(e) => setMsForm({ ...msForm, name: e.target.value })} placeholder="e.g. First 100k" className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Description</Label>
                <Input value={msForm.description} onChange={(e) => setMsForm({ ...msForm, description: e.target.value })} placeholder="Optional description" className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Target Date</Label>
                <Input type="date" value={msForm.target_date} onChange={(e) => setMsForm({ ...msForm, target_date: e.target.value })} className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <div>
                <Label className="text-[12px] font-semibold text-muted-foreground mb-1.5 block">Target Net Worth (optional)</Label>
                <Input type="number" value={msForm.target_net_worth} onChange={(e) => setMsForm({ ...msForm, target_net_worth: e.target.value })} placeholder="100000" className="h-11 rounded-xl bg-muted border-0" />
              </div>
              <button
                onClick={createMilestone}
                className="w-full h-11 rounded-xl bg-primary text-primary-foreground text-[14px] font-semibold cursor-pointer shadow-[0_10px_24px_-10px_rgba(59,130,246,0.4)] hover:opacity-90 transition-opacity mt-1"
              >
                Create Milestone
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
