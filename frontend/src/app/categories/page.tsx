"use client";

import { useEffect, useState } from "react";
import { api, Category, MerchantRule } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Plus, Trash2, Tag, Store, Search, Pencil, ChevronRight } from "lucide-react";

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

export default function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [merchants, setMerchants] = useState<MerchantRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [merchantSearch, setMerchantSearch] = useState("");

  // New category form
  const [newCatName, setNewCatName] = useState("");
  const [newCatType, setNewCatType] = useState("expense");
  const [newCatParent, setNewCatParent] = useState("");

  // New merchant form
  const [newMerchant, setNewMerchant] = useState({ name: "", patterns: "", category_id: "" });

  // Edit merchant
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
    await api.createCategory({
      name: newCatName.trim(),
      type: newCatType,
      parent_id: newCatParent || undefined,
    });
    setNewCatName("");
    setNewCatParent("");
    load();
  };

  const handleCreateMerchant = async () => {
    if (!newMerchant.name.trim() || !newMerchant.patterns.trim()) return;
    await api.createMerchant({
      name: newMerchant.name.trim(),
      patterns: newMerchant.patterns.trim().toLowerCase(),
      default_category_id: newMerchant.category_id || undefined,
    });
    setNewMerchant({ name: "", patterns: "", category_id: "" });
    load();
  };

  const handleUpdateMerchant = async (id: string) => {
    await api.updateMerchant(id, {
      name: editForm.name || undefined,
      patterns: editForm.patterns || undefined,
      default_category_id: editForm.category_id || undefined,
    });
    setEditingId(null);
    load();
  };

  const handleDeleteMerchant = async (id: string) => {
    await api.deleteMerchant(id);
    load();
  };

  const startEdit = (m: MerchantRule) => {
    setEditingId(m.id);
    setEditForm({ name: m.name, patterns: m.patterns, category_id: m.default_category_id || "" });
  };

  const filteredMerchants = merchantSearch
    ? merchants.filter((m) =>
        m.name.toLowerCase().includes(merchantSearch.toLowerCase()) ||
        m.patterns.toLowerCase().includes(merchantSearch.toLowerCase())
      )
    : merchants;

  const { parents, childMap } = buildCategoryTree(categories);

  // Grouped select options for category dropdowns
  const categoryOptions = (() => {
    const opts: { value: string; label: string; isParent?: boolean }[] = [];
    for (const p of parents.sort((a, b) => a.name.localeCompare(b.name))) {
      const kids = childMap[p.id] || [];
      if (kids.length > 0) {
        opts.push({ value: p.id, label: p.name, isParent: true });
        for (const k of kids.sort((a, b) => a.name.localeCompare(b.name))) {
          opts.push({ value: k.id, label: `  ${k.name}` });
        }
      } else {
        opts.push({ value: p.id, label: p.name });
      }
    }
    return opts;
  })();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Categories & Rules</h1>

      <Tabs defaultValue="categories">
        <TabsList>
          <TabsTrigger value="categories"><Tag className="h-4 w-4 mr-1" />Categories ({categories.length})</TabsTrigger>
          <TabsTrigger value="rules"><Store className="h-4 w-4 mr-1" />Merchant Rules ({merchants.length})</TabsTrigger>
        </TabsList>

        {/* Categories */}
        <TabsContent value="categories" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Add Category</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <Label className="text-xs">Name</Label>
                  <Input
                    placeholder="e.g. Gym"
                    value={newCatName}
                    onChange={(e) => setNewCatName(e.target.value)}
                    className="text-sm"
                  />
                </div>
                <div className="w-32">
                  <Label className="text-xs">Type</Label>
                  <select
                    className="w-full rounded-md border bg-background px-2 py-2 text-sm"
                    value={newCatType}
                    onChange={(e) => setNewCatType(e.target.value)}
                  >
                    <option value="expense">Expense</option>
                    <option value="income">Income</option>
                    <option value="transfer">Transfer</option>
                  </select>
                </div>
                <div className="w-40">
                  <Label className="text-xs">Parent (optional)</Label>
                  <select
                    className="w-full rounded-md border bg-background px-2 py-2 text-sm"
                    value={newCatParent}
                    onChange={(e) => setNewCatParent(e.target.value)}
                  >
                    <option value="">None (top-level)</option>
                    {parents.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <Button onClick={handleCreateCategory} size="sm">
                  <Plus className="h-4 w-4 mr-1" />Add
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Category Hierarchy</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-1">
                {parents.sort((a, b) => a.name.localeCompare(b.name)).map((p) => {
                  const kids = (childMap[p.id] || []).sort((a, b) => a.name.localeCompare(b.name));
                  return (
                    <div key={p.id}>
                      <div className="flex items-center gap-2 p-2 rounded-lg hover:bg-accent/50">
                        <div className={`w-3 h-3 rounded-full ${
                          p.type === "income" ? "bg-gain" : p.type === "transfer" ? "bg-primary" : "bg-loss"
                        }`} />
                        <span className="font-medium text-sm">{p.name}</span>
                        <Badge variant="secondary" className="text-[10px] capitalize">{p.type}</Badge>
                        {kids.length > 0 && (
                          <span className="text-xs text-muted-foreground ml-auto">{kids.length} sub</span>
                        )}
                      </div>
                      {kids.length > 0 && (
                        <div className="ml-6 border-l pl-3 space-y-0.5">
                          {kids.map((k) => (
                            <div key={k.id} className="flex items-center gap-2 py-1 px-2 rounded hover:bg-accent/30">
                              <ChevronRight className="h-3 w-3 text-muted-foreground" />
                              <span className="text-sm">{k.name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Merchant Rules */}
        <TabsContent value="rules" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Add Merchant Rule</CardTitle>
              <p className="text-xs text-muted-foreground">
                When a transaction description contains any of the patterns, it auto-categorizes to the selected category.
              </p>
            </CardHeader>
            <CardContent>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <Label className="text-xs">Merchant Name</Label>
                  <Input
                    placeholder="e.g. Starbucks"
                    value={newMerchant.name}
                    onChange={(e) => setNewMerchant({ ...newMerchant, name: e.target.value })}
                    className="text-sm"
                  />
                </div>
                <div className="flex-1">
                  <Label className="text-xs">Match Patterns (pipe-separated)</Label>
                  <Input
                    placeholder="e.g. starbucks|star bucks"
                    value={newMerchant.patterns}
                    onChange={(e) => setNewMerchant({ ...newMerchant, patterns: e.target.value })}
                    className="text-sm font-mono"
                  />
                </div>
                <div className="w-48">
                  <Label className="text-xs">Category</Label>
                  <select
                    className="w-full rounded-md border bg-background px-2 py-2 text-sm"
                    value={newMerchant.category_id}
                    onChange={(e) => setNewMerchant({ ...newMerchant, category_id: e.target.value })}
                  >
                    <option value="">Select...</option>
                    {categoryOptions.map((o) => (
                      <option key={o.value} value={o.value} className={o.isParent ? "font-bold" : ""}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <Button onClick={handleCreateMerchant} size="sm">
                  <Plus className="h-4 w-4 mr-1" />Add
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">All Rules</CardTitle>
                <div className="relative w-64">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search rules..."
                    value={merchantSearch}
                    onChange={(e) => setMerchantSearch(e.target.value)}
                    className="pl-9 text-sm"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading...</p>
              ) : (
                <div className="max-h-[500px] overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Merchant</TableHead>
                        <TableHead>Patterns</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead className="text-right w-24">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredMerchants.map((m) => (
                        <TableRow key={m.id}>
                          {editingId === m.id ? (
                            <>
                              <TableCell>
                                <Input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} className="text-sm h-8" />
                              </TableCell>
                              <TableCell>
                                <Input value={editForm.patterns} onChange={(e) => setEditForm({ ...editForm, patterns: e.target.value })} className="text-sm h-8 font-mono" />
                              </TableCell>
                              <TableCell>
                                <select
                                  className="rounded-md border bg-background px-2 py-1 text-sm"
                                  value={editForm.category_id}
                                  onChange={(e) => setEditForm({ ...editForm, category_id: e.target.value })}
                                >
                                  <option value="">--</option>
                                  {categoryOptions.map((o) => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                  ))}
                                </select>
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex justify-end gap-1">
                                  <Button size="sm" variant="ghost" onClick={() => handleUpdateMerchant(m.id)}>Save</Button>
                                  <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                                </div>
                              </TableCell>
                            </>
                          ) : (
                            <>
                              <TableCell className="font-medium">{m.name}</TableCell>
                              <TableCell>
                                <code className="text-xs text-muted-foreground">{m.patterns}</code>
                              </TableCell>
                              <TableCell>
                                {m.category_name ? (
                                  <Badge variant="secondary">{m.category_name}</Badge>
                                ) : (
                                  <span className="text-muted-foreground">--</span>
                                )}
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex justify-end gap-1">
                                  <Button size="icon" variant="ghost" onClick={() => startEdit(m)}>
                                    <Pencil className="h-3 w-3" />
                                  </Button>
                                  <Button size="icon" variant="ghost" onClick={() => handleDeleteMerchant(m.id)}>
                                    <Trash2 className="h-3 w-3 text-muted-foreground" />
                                  </Button>
                                </div>
                              </TableCell>
                            </>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
