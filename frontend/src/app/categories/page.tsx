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
import { Plus, Trash2, Tag, Store, Search, Pencil } from "lucide-react";

export default function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [merchants, setMerchants] = useState<MerchantRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [merchantSearch, setMerchantSearch] = useState("");

  // New category form
  const [newCatName, setNewCatName] = useState("");
  const [newCatType, setNewCatType] = useState("expense");

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
    await api.createCategory({ name: newCatName.trim(), type: newCatType });
    setNewCatName("");
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

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Categories & Rules</h1>

      <Tabs defaultValue="rules">
        <TabsList>
          <TabsTrigger value="rules"><Store className="h-4 w-4 mr-1" />Merchant Rules ({merchants.length})</TabsTrigger>
          <TabsTrigger value="categories"><Tag className="h-4 w-4 mr-1" />Categories ({categories.length})</TabsTrigger>
        </TabsList>

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
                <div className="w-40">
                  <Label className="text-xs">Category</Label>
                  <select
                    className="w-full rounded-md border bg-background px-2 py-2 text-sm"
                    value={newMerchant.category_id}
                    onChange={(e) => setNewMerchant({ ...newMerchant, category_id: e.target.value })}
                  >
                    <option value="">Select...</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
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
                                  <option value="">—</option>
                                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
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
                                  <span className="text-muted-foreground">—</span>
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
                    placeholder="e.g. Subscriptions"
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
                <Button onClick={handleCreateCategory} size="sm">
                  <Plus className="h-4 w-4 mr-1" />Add
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">All Categories</CardTitle></CardHeader>
            <CardContent>
              <div className="grid gap-2 md:grid-cols-3">
                {categories.map((c) => (
                  <div key={c.id} className="flex items-center justify-between p-3 rounded-lg border">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full ${
                        c.type === "income" ? "bg-green-500" : c.type === "transfer" ? "bg-blue-500" : "bg-red-500"
                      }`} />
                      <span className="text-sm font-medium">{c.name}</span>
                    </div>
                    <Badge variant="secondary" className="text-xs capitalize">{c.type}</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
