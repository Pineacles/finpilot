"use client";

import { useState } from "react";
import { Loader2, Pencil, Plus, Store, Trash2, Check, X } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { CategoryPill } from "@/components/category-pill";
import { cn } from "@/lib/format";
import { groupCategories } from "@/lib/categories";
import {
  useMerchantsQuery, useCategoriesQuery, useCreateMerchant, useUpdateMerchant, useDeleteMerchant,
} from "@/hooks/queries";
import { MerchantRule } from "@/lib/api";

function formatCreated(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("de-CH");
}

const emptyNewForm = { name: "", patterns: "", default_category_id: "" };

export default function MerchantsPage() {
  const merchantsQuery = useMerchantsQuery();
  const categoriesQuery = useCategoriesQuery();
  const createMerchant = useCreateMerchant();
  const updateMerchant = useUpdateMerchant();
  const deleteMerchant = useDeleteMerchant();

  const merchants = merchantsQuery.data ?? [];
  const categories = categoriesQuery.data ?? [];
  const groupedCategories = groupCategories(categories);

  const [newForm, setNewForm] = useState(emptyNewForm);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ name: "", patterns: "", default_category_id: "" });
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const categoryName = (id: string | null) => categories.find((c) => c.id === id)?.name ?? null;

  const startEdit = (m: MerchantRule) => {
    setEditingId(m.id);
    setEditForm({ name: m.name, patterns: m.patterns, default_category_id: m.default_category_id ?? "" });
  };

  const cancelEdit = () => setEditingId(null);

  const saveEdit = async (id: string) => {
    await updateMerchant.mutateAsync({
      id,
      data: {
        name: editForm.name,
        patterns: editForm.patterns,
        default_category_id: editForm.default_category_id || undefined,
      },
    });
    setEditingId(null);
  };

  const handleDelete = async (m: MerchantRule) => {
    if (!confirm(`Delete the rule for "${m.name}"? Future imports won't auto-categorize it via this rule anymore.`)) return;
    setDeletingId(m.id);
    try {
      await deleteMerchant.mutateAsync(m.id);
    } finally {
      setDeletingId(null);
    }
  };

  const handleCreate = async () => {
    setCreateError("");
    if (!newForm.name.trim() || !newForm.patterns.trim()) {
      setCreateError("Name and at least one pattern are required.");
      return;
    }
    setCreating(true);
    try {
      await createMerchant.mutateAsync({
        name: newForm.name.trim(),
        patterns: newForm.patterns.trim(),
        default_category_id: newForm.default_category_id || undefined,
      });
      setNewForm(emptyNewForm);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create rule");
    } finally {
      setCreating(false);
    }
  };

  const loading = merchantsQuery.isLoading || categoriesQuery.isLoading;

  return (
    <div className="space-y-6">
      <p className="text-[14px] text-muted-foreground">
        These rules steer future auto-categorization — when a transaction&apos;s merchant matches a pattern below, it gets the default category automatically on import.
      </p>

      {/* Create form */}
      <GlassCard className="space-y-4">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center h-8 w-8 rounded-xl bg-primary/10">
            <Plus className="h-4 w-4 text-primary" />
          </div>
          <h3 className="text-[15px] font-semibold">New rule</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_1.4fr_1fr_auto] gap-3">
          <input
            placeholder="Merchant name (e.g. Netflix)"
            value={newForm.name}
            onChange={(e) => setNewForm({ ...newForm, name: e.target.value })}
            className="h-11 rounded-xl bg-accent px-3 text-[14px] outline-none focus:ring-2 focus:ring-primary/30"
          />
          <input
            placeholder="Patterns, pipe-separated (e.g. netflix|nflx)"
            value={newForm.patterns}
            onChange={(e) => setNewForm({ ...newForm, patterns: e.target.value })}
            className="h-11 rounded-xl bg-accent px-3 text-[14px] outline-none focus:ring-2 focus:ring-primary/30"
          />
          <select
            value={newForm.default_category_id}
            onChange={(e) => setNewForm({ ...newForm, default_category_id: e.target.value })}
            className="h-11 rounded-xl bg-accent px-3 text-[14px] border-0 outline-none cursor-pointer"
          >
            <option value="">No default category</option>
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
            onClick={handleCreate}
            disabled={creating}
            className="h-11 px-5 rounded-xl bg-primary text-primary-foreground font-medium text-[14px] hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin mx-auto" /> : "Add rule"}
          </button>
        </div>
        {createError && <p className="text-[13px] text-loss">{createError}</p>}
      </GlassCard>

      {/* Table */}
      <GlassCard>
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : merchants.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Store className="h-16 w-16 text-muted-foreground/20 mb-4" />
            <p className="text-[15px] font-medium text-muted-foreground">No merchant rules yet</p>
            <p className="text-[13px] text-muted-foreground/60 mt-1">Add one above, or categorize a transaction to create one automatically</p>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-6 px-6">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border text-[11px] text-muted-foreground uppercase tracking-[0.3px]">
                  <th className="text-left font-semibold pb-3 pr-4">Name</th>
                  <th className="text-left font-semibold pb-3 pr-4">Patterns</th>
                  <th className="text-left font-semibold pb-3 pr-4">Default category</th>
                  <th className="text-left font-semibold pb-3 pr-4">Created</th>
                  <th className="pb-3 w-20" />
                </tr>
              </thead>
              <tbody>
                {merchants.map((m) => {
                  const isEditing = editingId === m.id;
                  return (
                    <tr key={m.id} className="group border-b border-border/50 transition-colors hover:bg-accent/50">
                      <td className="py-3 pr-4">
                        {isEditing ? (
                          <input
                            value={editForm.name}
                            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                            className="h-9 w-full rounded-xl bg-accent px-3 text-[14px] outline-none focus:ring-2 focus:ring-primary/30"
                            autoFocus
                          />
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{m.name}</span>
                            {m.is_system && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground uppercase tracking-wide">System</span>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {isEditing ? (
                          <input
                            value={editForm.patterns}
                            onChange={(e) => setEditForm({ ...editForm, patterns: e.target.value })}
                            className="h-9 w-full rounded-xl bg-accent px-3 text-[13px] outline-none focus:ring-2 focus:ring-primary/30 font-mono"
                          />
                        ) : (
                          <span className="text-muted-foreground font-mono text-[12px] truncate block max-w-[280px]">{m.patterns}</span>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        {isEditing ? (
                          <select
                            value={editForm.default_category_id}
                            onChange={(e) => setEditForm({ ...editForm, default_category_id: e.target.value })}
                            className="h-9 rounded-xl bg-accent px-3 text-[13px] border-0 outline-none cursor-pointer"
                          >
                            <option value="">No default category</option>
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
                        ) : m.default_category_id ? (
                          <CategoryPill name={m.category_name ?? categoryName(m.default_category_id) ?? "—"} />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap text-muted-foreground tabular-nums">
                        {formatCreated(m.created_at)}
                      </td>
                      <td className="py-3 text-right">
                        {isEditing ? (
                          <div className="flex items-center gap-1 justify-end">
                            <button onClick={() => saveEdit(m.id)} className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-gain">
                              <Check className="h-4 w-4" />
                            </button>
                            <button onClick={cancelEdit} className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-loss">
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        ) : (
                          <div className={cn("flex items-center gap-0.5 justify-end opacity-0 group-hover:opacity-100 transition-opacity")}>
                            <button onClick={() => startEdit(m)} className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground">
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(m)}
                              disabled={deletingId === m.id}
                              className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground hover:text-loss"
                            >
                              {deletingId === m.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
