"use client";

import { useEffect, useState } from "react";
import { api, Budget, Category } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Trash2 } from "lucide-react";

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Budgets</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger>
            <Button><Plus className="h-4 w-4 mr-2" />New Budget</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Create Budget</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div><Label>Amount (CHF)</Label><Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
              <div>
                <Label>Category (optional)</Label>
                <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
                  <option value="">All categories</option>
                  {categories.filter((c) => c.type === "expense").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <Label>Period</Label>
                <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })}>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="yearly">Yearly</option>
                </select>
              </div>
              <Button onClick={handleCreate} className="w-full">Create</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : budgets.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-muted-foreground">No budgets yet. Create your first budget to start tracking spending.</CardContent></Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {budgets.map((b) => {
            const over = b.pct_used > 100;
            return (
              <Card key={b.id}>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <div>
                    <CardTitle className="text-base">{b.name}</CardTitle>
                    <p className="text-xs text-muted-foreground capitalize">{b.period}{b.category_name ? ` · ${b.category_name}` : ""}</p>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => handleDelete(b.id)}>
                    <Trash2 className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </CardHeader>
                <CardContent>
                  <div className="flex justify-between text-sm mb-2">
                    <span className={over ? "text-red-500 font-medium" : ""}>{formatCurrency(b.spent)} spent</span>
                    <span className="text-muted-foreground">of {formatCurrency(b.amount)}</span>
                  </div>
                  <Progress value={Math.min(b.pct_used, 100)} className={over ? "[&>div]:bg-red-500" : ""} />
                  <p className="text-xs text-muted-foreground mt-2">
                    {over ? `Over by ${formatCurrency(b.spent - b.amount)}` : `${formatCurrency(b.remaining)} remaining`}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
