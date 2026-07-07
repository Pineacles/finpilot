"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Category, TransactionItem } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/format";
import { CategoryPill } from "@/components/category-pill";
import { groupCategories } from "@/lib/categories";
import {
  ChevronLeft, ChevronRight, Check, X, Pencil, ArrowUpRight, ArrowDownLeft,
  ReceiptText, Loader2, Trash2,
} from "lucide-react";

const PAGE_SIZE = 25;

interface TransactionsTableProps {
  transactions: TransactionItem[]; // already search-filtered; this component paginates internally
  categories: Category[];
  loading: boolean;
  hasAnyTransactions: boolean;
  searchActive: boolean;
  highlightId?: string;
  onUpdate: (
    id: string,
    data: { merchant: string; notes?: string; apply_merchant_to_all: boolean; apply_category_to_all: boolean; description_filter?: string },
  ) => Promise<void>;
  onCategorize: (id: string, categoryId: string) => Promise<void>;
  onDeleteOne: (id: string) => Promise<void>;
  onBulkDelete: (ids: string[]) => Promise<number>;
}

export function TransactionsTable({
  transactions, categories, loading, hasAnyTransactions, searchActive, highlightId,
  onUpdate, onCategorize, onDeleteOne, onBulkDelete,
}: TransactionsTableProps) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [lastDeletedCount, setLastDeletedCount] = useState<number | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editMerchant, setEditMerchant] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [editApplyMerchant, setEditApplyMerchant] = useState(true);
  const [editApplyCategory, setEditApplyCategory] = useState(true);
  const [editDescFilter, setEditDescFilter] = useState("");
  const [editOriginalMerchant, setEditOriginalMerchant] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [categoryDropdownId, setCategoryDropdownId] = useState<string | null>(null);
  const [categoryLoading, setCategoryLoading] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLTableRowElement>(null);

  const groupedCategories = useMemo(() => groupCategories(categories), [categories]);

  const totalPages = Math.max(1, Math.ceil(transactions.length / PAGE_SIZE));
  const paginated = transactions.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Reset to page 0 whenever the filtered set changes size/search state changes shape
  useEffect(() => { setPage(0); }, [searchActive]);

  // Jump to the page containing the highlighted transaction
  useEffect(() => {
    if (!highlightId) return;
    const idx = transactions.findIndex((t) => t.id === highlightId);
    if (idx >= 0) {
      const targetPage = Math.floor(idx / PAGE_SIZE);
      if (targetPage !== page) setPage(targetPage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightId, transactions]);

  useEffect(() => {
    if (highlightId && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightId, page, paginated]);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setCategoryDropdownId(null);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const startEditing = (txn: TransactionItem) => {
    setEditingId(txn.id);
    setEditMerchant(txn.merchant);
    setEditNotes(txn.notes ?? "");
    setEditOriginalMerchant(txn.merchant);
    setEditApplyMerchant(true);
    setEditApplyCategory(true);
    setEditDescFilter("");
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditMerchant("");
    setEditNotes("");
    setEditOriginalMerchant("");
    setEditDescFilter("");
  };

  const editSiblingCount = useMemo(() => {
    if (!editOriginalMerchant) return 0;
    return transactions.filter((t) => t.merchant === editOriginalMerchant && t.id !== editingId).length;
  }, [editOriginalMerchant, editingId, transactions]);

  const editDistinctDescriptions = useMemo(() => {
    if (!editOriginalMerchant) return [];
    const notes = new Set<string>();
    transactions
      .filter((t) => t.merchant === editOriginalMerchant)
      .forEach((t) => { if (t.notes) notes.add(t.notes.toLowerCase().split(/\s+/)[0]); });
    return Array.from(notes).slice(0, 10);
  }, [editOriginalMerchant, transactions]);

  const editFilteredCount = useMemo(() => {
    if (!editOriginalMerchant || !editApplyMerchant) return 0;
    return transactions.filter((t) => {
      if (t.merchant !== editOriginalMerchant || t.id === editingId) return false;
      if (editDescFilter) return (t.notes ?? "").toLowerCase().includes(editDescFilter.toLowerCase());
      return true;
    }).length;
  }, [editOriginalMerchant, editingId, editApplyMerchant, editDescFilter, transactions]);

  const saveEditing = async () => {
    if (!editingId) return;
    setSavingEdit(true);
    try {
      await onUpdate(editingId, {
        merchant: editMerchant,
        notes: editNotes || undefined,
        apply_merchant_to_all: editApplyMerchant,
        apply_category_to_all: editApplyCategory,
        description_filter: editDescFilter || undefined,
      });
      cancelEditing();
    } finally {
      setSavingEdit(false);
    }
  };

  const handleCategoryChange = async (txnId: string, categoryId: string) => {
    setCategoryLoading(txnId);
    setCategoryDropdownId(null);
    try {
      await onCategorize(txnId, categoryId);
    } finally {
      setCategoryLoading(null);
    }
  };

  const handleDeleteOne = async (txn: TransactionItem) => {
    if (!confirm(`Delete this transaction (${txn.merchant}, ${formatCurrency(txn.amount, txn.currency)})?`)) return;
    setDeletingId(txn.id);
    try {
      await onDeleteOne(txn.id);
      setSelected((prev) => { const next = new Set(prev); next.delete(txn.id); return next; });
    } finally {
      setDeletingId(null);
    }
  };

  const toggleRow = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllOnPage = () => {
    const pageIds = paginated.map((t) => t.id);
    const allSelected = pageIds.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      if (allSelected) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const handleBulkDelete = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} selected transaction${selected.size !== 1 ? "s" : ""}? This cannot be undone.`)) return;
    setBulkDeleting(true);
    try {
      const deleted = await onBulkDelete(Array.from(selected));
      setLastDeletedCount(deleted);
      setSelected(new Set());
      setTimeout(() => setLastDeletedCount(null), 4000);
    } finally {
      setBulkDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (transactions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <ReceiptText className="h-16 w-16 text-muted-foreground/20 mb-4" />
        {!hasAnyTransactions ? (
          <>
            <p className="text-[15px] font-medium text-muted-foreground">No transactions yet</p>
            <p className="text-[13px] text-muted-foreground/60 mt-1">Import a CSV, XML, or TSV file to get started</p>
          </>
        ) : (
          <>
            <p className="text-[15px] font-medium text-muted-foreground">No matching transactions</p>
            <p className="text-[13px] text-muted-foreground/60 mt-1">Try adjusting your search terms</p>
          </>
        )}
      </div>
    );
  }

  const pageIds = paginated.map((t) => t.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  return (
    <>
      {/* Bulk selection bar */}
      {selected.size > 0 && (
        <div className="flex items-center justify-between rounded-xl bg-primary/10 px-4 py-2.5 mb-1">
          <span className="text-[13px] font-medium text-primary">{selected.size} selected</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSelected(new Set())}
              className="text-[13px] font-medium text-muted-foreground hover:text-foreground cursor-pointer"
            >
              Clear
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
              className="flex items-center gap-1.5 rounded-xl px-3 h-8 text-[13px] font-medium bg-loss text-white active:scale-[0.98] cursor-pointer transition-all disabled:opacity-50"
            >
              {bulkDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              Delete
            </button>
          </div>
        </div>
      )}
      {lastDeletedCount !== null && (
        <p className="text-[13px] text-muted-foreground mb-1">Deleted {lastDeletedCount} transaction{lastDeletedCount !== 1 ? "s" : ""}.</p>
      )}

      <div className="overflow-x-auto -mx-6 px-6">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border text-[11px] text-muted-foreground uppercase tracking-[0.3px]">
              <th className="w-8 pb-3 pr-2">
                <input type="checkbox" checked={allPageSelected} onChange={toggleAllOnPage} className="rounded accent-primary cursor-pointer" />
              </th>
              <th className="text-left font-semibold pb-3 pr-4">Date</th>
              <th className="text-left font-semibold pb-3 pr-4">Merchant</th>
              <th className="text-left font-semibold pb-3 pr-4">Description</th>
              <th className="text-left font-semibold pb-3 pr-4">Category</th>
              <th className="text-right font-semibold pb-3 pr-4">Amount</th>
              <th className="pb-3 w-16" />
            </tr>
          </thead>
          <tbody>
            {paginated.map((txn) => {
              const isEditing = editingId === txn.id;
              const isHighlighted = txn.id === highlightId;
              const isIncome = txn.amount >= 0;

              return (
                <React.Fragment key={txn.id}>
                  <tr
                    ref={isHighlighted ? highlightRef : undefined}
                    className={cn(
                      "group border-b border-border/50 transition-colors hover:bg-accent/50",
                      isHighlighted && "animate-highlight-pulse bg-yellow-400/10 ring-1 ring-yellow-400/40",
                      isEditing && "bg-accent/20 border-b-0",
                    )}
                  >
                    <td className="py-3 pr-2">
                      <input
                        type="checkbox"
                        checked={selected.has(txn.id)}
                        onChange={() => toggleRow(txn.id)}
                        className="rounded accent-primary cursor-pointer"
                      />
                    </td>

                    <td className="py-3 pr-4 whitespace-nowrap text-[13px] text-muted-foreground tabular-nums">
                      {formatDate(txn.date)}
                    </td>

                    <td className="py-3 pr-4">
                      {isEditing ? (
                        <input
                          value={editMerchant}
                          onChange={(e) => setEditMerchant(e.target.value)}
                          className="h-9 w-full rounded-xl bg-accent px-3 text-[15px] outline-none focus:ring-2 focus:ring-primary/30"
                          autoFocus
                        />
                      ) : (
                        <div className="flex items-center gap-2.5">
                          <div className={cn("flex items-center justify-center h-8 w-8 rounded-full shrink-0", isIncome ? "bg-emerald-500/10" : "bg-rose-500/10")}>
                            {isIncome ? <ArrowDownLeft className="h-3.5 w-3.5 text-emerald-500" /> : <ArrowUpRight className="h-3.5 w-3.5 text-rose-500" />}
                          </div>
                          <span className="font-medium truncate max-w-[200px]">{txn.merchant}</span>
                        </div>
                      )}
                    </td>

                    <td className="py-3 pr-4">
                      {isEditing ? (
                        <input
                          value={editNotes}
                          onChange={(e) => setEditNotes(e.target.value)}
                          placeholder="Notes..."
                          className="h-9 w-full rounded-xl bg-accent px-3 text-[15px] outline-none placeholder:text-muted-foreground/40 focus:ring-2 focus:ring-primary/30"
                        />
                      ) : (
                        <span className="text-[13px] text-muted-foreground truncate block max-w-[220px]">{txn.notes || "—"}</span>
                      )}
                    </td>

                    <td className="py-3 pr-4 relative">
                      {categoryLoading === txn.id ? (
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      ) : (
                        <>
                          <button
                            onClick={() => setCategoryDropdownId(categoryDropdownId === txn.id ? null : txn.id)}
                            className="cursor-pointer active:scale-[0.98] transition-all"
                          >
                            <CategoryPill name={txn.category_name ?? "Uncategorized"} />
                          </button>
                          {txn.parent_category_name && txn.parent_category_name !== txn.category_name && (
                            <span className="block text-[11px] text-muted-foreground/60 mt-0.5 pl-1">{txn.parent_category_name}</span>
                          )}
                        </>
                      )}

                      {categoryDropdownId === txn.id && (
                        <div ref={dropdownRef} className="absolute z-50 top-full left-0 mt-1 w-56 bg-popover rounded-2xl border border-border shadow-lg p-2 max-h-64 overflow-y-auto">
                          {groupedCategories.map((g) => (
                            <div key={g.id}>
                              <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider px-2 pt-2 pb-1">{g.name}</div>
                              {g.children.length > 0 ? (
                                g.children.map((c) => (
                                  <button
                                    key={c.id}
                                    onClick={() => handleCategoryChange(txn.id, c.id)}
                                    className={cn("w-full text-left px-2 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors", "hover:bg-accent active:scale-[0.98]", txn.category_id === c.id && "bg-primary/10 text-primary")}
                                  >
                                    {c.name}
                                  </button>
                                ))
                              ) : (
                                <button
                                  onClick={() => handleCategoryChange(txn.id, g.id)}
                                  className={cn("w-full text-left px-2 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors", "hover:bg-accent active:scale-[0.98]", txn.category_id === g.id && "bg-primary/10 text-primary")}
                                >
                                  {g.name}
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </td>

                    <td className={cn("py-3 pr-4 text-right whitespace-nowrap font-mono tabular-nums text-[14px] font-semibold", isIncome ? "text-gain" : "text-loss")}>
                      {formatCurrency(txn.amount, txn.currency)}
                    </td>

                    <td className="py-3 text-right">
                      {isEditing ? (
                        <div className="flex items-center gap-1 justify-end">
                          <button onClick={saveEditing} disabled={savingEdit} className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-gain">
                            {savingEdit ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                          </button>
                          <button onClick={cancelEditing} className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-loss">
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-0.5 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => startEditing(txn)} className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground">
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDeleteOne(txn)}
                            disabled={deletingId === txn.id}
                            className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground hover:text-loss"
                          >
                            {deletingId === txn.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  {isEditing && editSiblingCount > 0 && (
                    <tr className="border-b border-border/50 bg-accent/10">
                      <td colSpan={7} className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-4 text-[13px]">
                          <span className="text-muted-foreground font-medium">
                            {editSiblingCount} other &quot;{editOriginalMerchant}&quot; transaction{editSiblingCount !== 1 ? "s" : ""}
                          </span>
                          <label className="flex items-center gap-1.5 cursor-pointer select-none">
                            <input type="checkbox" checked={editApplyMerchant} onChange={(e) => setEditApplyMerchant(e.target.checked)} className="rounded accent-primary cursor-pointer" />
                            <span>Rename all</span>
                          </label>
                          <label className="flex items-center gap-1.5 cursor-pointer select-none">
                            <input type="checkbox" checked={editApplyCategory} onChange={(e) => setEditApplyCategory(e.target.checked)} className="rounded accent-primary cursor-pointer" />
                            <span>Recategorize all</span>
                          </label>
                          {editDistinctDescriptions.length > 1 && (editApplyMerchant || editApplyCategory) && (
                            <div className="flex items-center gap-1.5">
                              <span className="text-muted-foreground">Only where description contains:</span>
                              <input
                                value={editDescFilter}
                                onChange={(e) => setEditDescFilter(e.target.value)}
                                placeholder="e.g. carvolution"
                                className="h-7 w-36 rounded-lg bg-accent px-2 text-[13px] outline-none focus:ring-2 focus:ring-primary/30"
                              />
                            </div>
                          )}
                          {(editApplyMerchant || editApplyCategory) && (
                            <span className={cn("text-[12px] px-2 py-0.5 rounded-lg font-medium", editFilteredCount > 0 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
                              {editFilteredCount} will be updated
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between pt-2">
        <p className="text-[13px] text-muted-foreground">
          {transactions.length} transaction{transactions.length !== 1 ? "s" : ""}{searchActive && " found"}
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="flex items-center justify-center h-9 w-9 rounded-xl bg-accent hover:bg-accent/80 active:scale-[0.98] cursor-pointer transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-[13px] text-muted-foreground tabular-nums min-w-[80px] text-center">Page {page + 1} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="flex items-center justify-center h-9 w-9 rounded-xl bg-accent hover:bg-accent/80 active:scale-[0.98] cursor-pointer transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}
