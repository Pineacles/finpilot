"use client";

import { useEffect, useState } from "react";
import { api, SavingsGoal, Milestone } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Plus, Target, Flag, CheckCircle2 } from "lucide-react";

export default function GoalsPage() {
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(true);
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
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Goals & Milestones</h1>

      <Tabs defaultValue="goals">
        <TabsList>
          <TabsTrigger value="goals"><Target className="h-4 w-4 mr-1" />Savings Goals</TabsTrigger>
          <TabsTrigger value="milestones"><Flag className="h-4 w-4 mr-1" />Milestones</TabsTrigger>
        </TabsList>

        <TabsContent value="goals" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Dialog open={goalOpen} onOpenChange={setGoalOpen}>
              <DialogTrigger><Button><Plus className="h-4 w-4 mr-2" />New Goal</Button></DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Create Savings Goal</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div><Label>Name</Label><Input value={goalForm.name} onChange={(e) => setGoalForm({ ...goalForm, name: e.target.value })} /></div>
                  <div><Label>Target Amount (CHF)</Label><Input type="number" value={goalForm.target_amount} onChange={(e) => setGoalForm({ ...goalForm, target_amount: e.target.value })} /></div>
                  <div><Label>Target Date (optional)</Label><Input type="date" value={goalForm.target_date} onChange={(e) => setGoalForm({ ...goalForm, target_date: e.target.value })} /></div>
                  <Button onClick={createGoal} className="w-full">Create</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {goals.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground">No savings goals yet.</CardContent></Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {goals.map((g) => (
                <Card key={g.id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{g.name}</CardTitle>
                    {g.target_date && <p className="text-xs text-muted-foreground">Target: {formatDate(g.target_date)}</p>}
                  </CardHeader>
                  <CardContent>
                    <div className="flex justify-between text-sm mb-2">
                      <span>{formatCurrency(g.current_amount)}</span>
                      <span className="text-muted-foreground">{formatCurrency(g.target_amount)}</span>
                    </div>
                    <Progress value={g.progress_pct} />
                    <p className="text-xs text-muted-foreground mt-2">{g.progress_pct.toFixed(1)}% complete</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="milestones" className="space-y-4 mt-4">
          <div className="flex justify-end">
            <Dialog open={msOpen} onOpenChange={setMsOpen}>
              <DialogTrigger><Button><Plus className="h-4 w-4 mr-2" />New Milestone</Button></DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>Create Milestone</DialogTitle></DialogHeader>
                <div className="space-y-4">
                  <div><Label>Name</Label><Input value={msForm.name} onChange={(e) => setMsForm({ ...msForm, name: e.target.value })} /></div>
                  <div><Label>Description</Label><Input value={msForm.description} onChange={(e) => setMsForm({ ...msForm, description: e.target.value })} /></div>
                  <div><Label>Target Date</Label><Input type="date" value={msForm.target_date} onChange={(e) => setMsForm({ ...msForm, target_date: e.target.value })} /></div>
                  <div><Label>Target Net Worth (optional)</Label><Input type="number" value={msForm.target_net_worth} onChange={(e) => setMsForm({ ...msForm, target_net_worth: e.target.value })} /></div>
                  <Button onClick={createMilestone} className="w-full">Create</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {milestones.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground">No milestones yet.</CardContent></Card>
          ) : (
            <div className="space-y-3">
              {milestones.map((m) => (
                <Card key={m.id}>
                  <CardContent className="flex items-center gap-4 py-4">
                    {m.achieved ? (
                      <CheckCircle2 className="h-6 w-6 text-green-500 shrink-0" />
                    ) : (
                      <Flag className="h-6 w-6 text-muted-foreground shrink-0" />
                    )}
                    <div className="flex-1">
                      <p className="font-medium">{m.name}</p>
                      {m.description && <p className="text-sm text-muted-foreground">{m.description}</p>}
                    </div>
                    <div className="text-right">
                      {m.target_date && <p className="text-sm">{formatDate(m.target_date)}</p>}
                      {m.target_net_worth && <p className="text-xs text-muted-foreground">{formatCurrency(m.target_net_worth)}</p>}
                      {m.achieved && <Badge variant="secondary" className="mt-1">Achieved</Badge>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
