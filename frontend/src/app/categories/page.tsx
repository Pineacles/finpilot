"use client";

import { useEffect, useState } from "react";
import { api, Category, MerchantRule } from "@/lib/api";
import { GlassCard } from "@/components/glass-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Plus, Trash2, Pencil, X, Check, Tag, Store, Search, ChevronRight } from "lucide-react";

function buildCategoryTree(categories: Category[]) {
  const parents = categories.filter((c) => !c.parent_id);
  const childMap: Record<string, Category[]> = {};
  for (const c of categories) {
    if (c.parent_id) {
      if (!childMap[c.parent_id]) childMap[c.parent_id] = [];
      childMap[c.parent_id].push(c);
    }
  }
  return { parents, childMap };
}

function buildCategoryOptions(categories: Category[]) {
  const { parents, childMap } = buildCategoryTree(categories);
  const opts: { value: string; label: string }[] = [];
  for (const p of parents.sort((a, b) => a.name.localeCompare(b.name))) {
    const kids = (childMap[p.id] || []).sort((a, b) => a.name.localeCompare(b.name));
    if (kids.length > 0) {
      opts.push({ value: p.id, label: p.name });
      for (const k of kids) opts.push({ value: k.id, label: `  ${k.name}` });
    } else {
      opts.push({ value: p.id, label: p.name });
    }
  }
  return opts;
}

export default function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [merchants, setMerchants] = useState<MerchantRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"categories" | "rules">("categories");
  const [merchantSearch, setMerchantSearch] = useState("");
  const [newCatName, setNewCatName] = useState("");
  const [newCatType, setNewCatType] = useState("expense");
  const [newCatParent, setNewCatParent] = useState("");
  const [newMerchant, setNewMerchant] = useState({ name: "", patterns: "", category_id: "" });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ name: "", patterns: "", category_id: "" });

  const load = () => {
    Promise.all([api.categories(), api.merchants()])
      .then(([c, m]) => { setCategories(c); setMerchants(m); })
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const handleCreateCategory = async () => {
    if (!newCatName.trim()) return;
    await api.createCategory({ name: newCatName.trim(), type: newCatType, parent_id: newCatParent || undefined });
    setNewCatName(""); setNewCatParent(""); load();
  };
  const handleCreateMerchant = async () => {
    if (!newMerchant.name.trim() || !newMerchant.patterns.trim()) return;
    await api.createMerchant({ name: newMerchant.name.trim(), patterns: newMerchant.patterns.trim().toLowerCase(), default_category_id: newMerchant.category_id || undefined });
    setNewMerchant({ name: "", patterns: "", category_id: "" }); load();
  };
  const handleUpdateMerchant = async (id: string) => {
    await api.updateMerchant(id, { name: editForm.name || undefined, patterns: editForm.patterns || undefined, default_category_id: editForm.category_id || undefined });
    setEditingId(null); load();
  };
  const handleDeleteMerchant = async (id: string) => { await api.deleteMerchant(id); load(); };

  const { parents, childMap } = buildCategoryTree(categories);
  const catOptions = buildCategoryOptions(categories);
  const filteredMerchants = merchantSearch
    ? merchants.filter(m => m.name.toLowerCase().includes(merchantSearch.toLowerCase()) || m.patterns.toLowerCase().includes(merchantSearch.toLowerCase()))
    : merchants;

  return (
    <div className="space-y-8 p-1">
      {/* Tabs */}
      <div className="flex gap-2">
        {(["categories", "rules"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-5 py-2.5 rounded-[14px] text-[14px] font-medium transition-all cursor-pointer capitalize flex items-center gap-2 ${tab === t ? "bg-primary text-primary-foreground" : "glass bg-card text-muted-foreground hover:text-foreground"}`}>
            {t === "categories" ? <Tag className="h-4 w-4" /> : <Store className="h-4 w-4" />}
            {t} ({t === "categories" ? categories.length : merchants.length})
          </button>
        ))}
      </div>

      {tab === "categories" ? (
        <>
          {/* Add Category */}
          <GlassCard delay={0.05}>
            <h2 className="text-[16px] font-semibold mb-4">Add Category</h2>
            <div className="flex items-end gap-3 flex-wrap">
              <div className="flex-1 min-w-[150px]">
                <label className="text-[13px] text-muted-foreground block mb-1.5">Name</label>
                <Input placeholder="e.g. Gym" value={newCatName} onChange={e => setNewCatName(e.target.value)} className="rounded-xl h-11" />
              </div>
              <div className="w-32">
                <label className="text-[13px] text-muted-foreground block mb-1.5">Type</label>
                <select className="w-full h-11 rounded-xl bg-muted px-3 text-[14px] border-0" value={newCatType} onChange={e => setNewCatType(e.target.value)}>
                  <option value="expense">Expense</option><option value="income">Income</option><option value="transfer">Transfer</option>
                </select>
              </div>
              <div className="w-40">
                <label className="text-[13px] text-muted-foreground block mb-1.5">Parent</label>
                <select className="w-full h-11 rounded-xl bg-muted px-3 text-[14px] border-0" value={newCatParent} onChange={e => setNewCatParent(e.target.value)}>
                  <option value="">None (top-level)</option>
                  {parents.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <Button onClick={handleCreateCategory} className="rounded-xl h-11 px-5"><Plus className="h-4 w-4 mr-1" />Add</Button>
            </div>
          </GlassCard>

          {/* Hierarchy */}
          <GlassCard delay={0.1}>
            <h2 className="text-[16px] font-semibold mb-4">Category Hierarchy</h2>
            {loading ? (
              <p className="text-[13px] text-muted-foreground py-4">Loading…</p>
            ) : categories.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground">
                <Tag className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-[13px]">No categories yet.</p>
              </div>
            ) : (
              <div className="space-y-1">
                {parents.sort((a, b) => a.name.localeCompare(b.name)).map(p => {
                  const kids = (childMap[p.id] || []).sort((a, b) => a.name.localeCompare(b.name));
                  return (
                    <div key={p.id}>
                      <div className="flex items-center gap-3 p-3 rounded-2xl hover:bg-muted/60 transition-colors">
                        <div
                          className={`w-3 h-3 rounded-full ${
                            p.type === "income" ? "bg-gain" : p.type === "transfer" ? "bg-blue-500" : "bg-loss"
                          }`}
                        />
                        <span className="font-medium text-[15px]">{p.name}</span>
                        <Badge variant="secondary" className="text-[11px] capitalize rounded-lg">{p.type}</Badge>
                        {kids.length > 0 && <span className="text-[13px] text-muted-foreground ml-auto">{kids.length} sub</span>}
                      </div>
                      {kids.length > 0 && (
                        <div className="ml-8 border-l border-border pl-4 space-y-0.5">
                          {kids.map(k => (
                            <div key={k.id} className="flex items-center gap-2 py-2 px-3 rounded-xl hover:bg-muted/60 transition-colors">
                              <ChevronRight className="h-3 w-3 text-muted-foreground" />
                              <span className="text-[15px]">{k.name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </GlassCard>
        </>
      ) : (
        <>
          {/* Add Merchant Rule */}
          <GlassCard delay={0.05}>
            <h2 className="text-[16px] font-semibold mb-2">Add Merchant Rule</h2>
            <p className="text-[13px] text-muted-foreground mb-4">When a transaction description contains any pattern, it auto-categorizes.</p>
            <div className="flex items-end gap-3 flex-wrap">
              <div className="flex-1 min-w-[120px]">
                <label className="text-[13px] text-muted-foreground block mb-1.5">Name</label>
                <Input placeholder="Starbucks" value={newMerchant.name} onChange={e => setNewMerchant({ ...newMerchant, name: e.target.value })} className="rounded-xl h-11" />
              </div>
              <div className="flex-1 min-w-[120px]">
                <label className="text-[13px] text-muted-foreground block mb-1.5">Patterns (pipe-separated)</label>
                <Input placeholder="starbucks|star bucks" value={newMerchant.patterns} onChange={e => setNewMerchant({ ...newMerchant, patterns: e.target.value })} className="rounded-xl h-11 font-mono text-[13px]" />
              </div>
              <div className="w-48">
                <label className="text-[13px] text-muted-foreground block mb-1.5">Category</label>
                <select className="w-full h-11 rounded-xl bg-muted px-3 text-[14px] border-0" value={newMerchant.category_id} onChange={e => setNewMerchant({ ...newMerchant, category_id: e.target.value })}>
                  <option value="">Select...</option>
                  {catOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <Button onClick={handleCreateMerchant} className="rounded-xl h-11 px-5"><Plus className="h-4 w-4 mr-1" />Add</Button>
            </div>
          </GlassCard>

          {/* Rules list */}
          <GlassCard delay={0.1}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[16px] font-semibold">All Rules</h2>
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input placeholder="Search rules..." value={merchantSearch} onChange={e => setMerchantSearch(e.target.value)} className="pl-9 rounded-xl h-10" />
              </div>
            </div>
            {filteredMerchants.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground">
                <Store className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-[13px]">{merchantSearch ? "No rules match your search." : "No merchant rules yet."}</p>
              </div>
            ) : (
              <div className="space-y-1 max-h-[500px] overflow-y-auto">
                {filteredMerchants.map(m => (
                  <div key={m.id} className="flex items-center justify-between p-3 rounded-2xl hover:bg-muted/60 transition-colors group">
                    {editingId === m.id ? (
                      <div className="flex items-center gap-2 flex-1">
                        <Input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} className="h-9 rounded-xl text-[14px]" />
                        <Input value={editForm.patterns} onChange={e => setEditForm({ ...editForm, patterns: e.target.value })} className="h-9 rounded-xl text-[14px] font-mono" />
                        <select className="h-9 rounded-xl bg-muted px-2 text-[14px] border-0" value={editForm.category_id} onChange={e => setEditForm({ ...editForm, category_id: e.target.value })}>
                          <option value="">--</option>
                          {catOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                        <button className="cursor-pointer" onClick={() => handleUpdateMerchant(m.id)}><Check className="h-4 w-4 text-gain" /></button>
                        <button className="cursor-pointer" onClick={() => setEditingId(null)}><X className="h-4 w-4 text-muted-foreground" /></button>
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center gap-4">
                          <span className="font-medium text-[15px]">{m.name}</span>
                          <code className="text-[12px] text-muted-foreground font-mono">{m.patterns}</code>
                        </div>
                        <div className="flex items-center gap-2">
                          {m.category_name ? <Badge variant="secondary" className="rounded-lg">{m.category_name}</Badge> : <span className="text-muted-foreground text-[12px]">--</span>}
                          <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              className="cursor-pointer p-1"
                              onClick={() => { setEditingId(m.id); setEditForm({ name: m.name, patterns: m.patterns, category_id: m.default_category_id || "" }); }}
                            >
                              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                            </button>
                            <button className="cursor-pointer p-1" onClick={() => handleDeleteMerchant(m.id)}>
                              <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                            </button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </GlassCard>
        </>
      )}
    </div>
  );
}
