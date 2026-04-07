"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  api,
  TransactionItem,
  Category,
  ImportResult,
  ImportLogEntry,
} from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/format";
import {
  Upload,
  Sparkles,
  Search,
  ChevronLeft,
  ChevronRight,
  Check,
  X,
  Pencil,
  Tag,
  ArrowUpRight,
  ArrowDownLeft,
  FileText,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ReceiptText,
  ListChecks,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  GlassCard                                                          */
/* ------------------------------------------------------------------ */
function GlassCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("glass bg-card rounded-3xl p-6", className)}
    >
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */
const PAGE_SIZE = 50;
const ACCEPTED_EXTENSIONS = ".csv,.xml,.tsv";

/* ------------------------------------------------------------------ */
/*  Inner page (needs useSearchParams inside Suspense)                 */
/* ------------------------------------------------------------------ */
function TransactionsInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  // URL params
  const urlSearch = searchParams.get("search") ?? "";
  const urlHighlight = searchParams.get("highlight") ?? "";

  // Data
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  // Search
  const [search, setSearch] = useState(urlSearch);
  const [debouncedSearch, setDebouncedSearch] = useState(urlSearch);

  // Pagination
  const [page, setPage] = useState(0);

  // Import
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importLogs, setImportLogs] = useState<ImportLogEntry[]>([]);
  const [importError, setImportError] = useState<string | null>(null);
  const [showConsole, setShowConsole] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const consoleRef = useRef<HTMLDivElement>(null);

  // Uncategorized panel
  const [selectedUncategorized, setSelectedUncategorized] = useState<Set<string>>(
    new Set(),
  );
  const [bulkCategoryId, setBulkCategoryId] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  // Inline editing
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editMerchant, setEditMerchant] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  // Category dropdown
  const [categoryDropdownId, setCategoryDropdownId] = useState<string | null>(null);
  const [categoryLoading, setCategoryLoading] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Highlight
  const highlightRef = useRef<HTMLTableRowElement>(null);

  /* ---- Load data ------------------------------------------------- */
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [txns, cats] = await Promise.all([
        api.transactions({ limit: 2000 }),
        api.categories(),
      ]);
      setTransactions(txns);
      setCategories(cats);
    } catch {
      // silently handle -- user sees empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* ---- Debounce search ------------------------------------------- */
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
      const params = new URLSearchParams(searchParams.toString());
      if (search) params.set("search", search);
      else params.delete("search");
      if (urlHighlight) params.set("highlight", urlHighlight);
      const qs = params.toString();
      router.replace(qs ? `?${qs}` : "?", { scroll: false });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  /* ---- Scroll to highlighted -------------------------------------- */
  useEffect(() => {
    if (urlHighlight && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [urlHighlight, transactions, page]);

  /* ---- Close category dropdown on outside click ------------------- */
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setCategoryDropdownId(null);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  /* ---- Filtered + paginated data --------------------------------- */
  const filtered = useMemo(() => {
    if (!debouncedSearch) return transactions;
    const q = debouncedSearch.toLowerCase();
    return transactions.filter(
      (t) =>
        t.merchant.toLowerCase().includes(q) ||
        (t.notes ?? "").toLowerCase().includes(q) ||
        (t.category_name ?? "").toLowerCase().includes(q) ||
        (t.parent_category_name ?? "").toLowerCase().includes(q),
    );
  }, [transactions, debouncedSearch]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // If highlight is set, jump to correct page
  useEffect(() => {
    if (!urlHighlight) return;
    const idx = filtered.findIndex((t) => t.id === urlHighlight);
    if (idx >= 0) {
      const targetPage = Math.floor(idx / PAGE_SIZE);
      if (targetPage !== page) setPage(targetPage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlHighlight, filtered]);

  const uncategorized = useMemo(
    () => transactions.filter((t) => !t.category_id),
    [transactions],
  );

  /* ---- Category helpers ------------------------------------------ */
  const groupedCategories = useMemo(() => {
    const parents = categories
      .filter((c) => !c.parent_id)
      .sort((a, b) => a.name.localeCompare(b.name));
    const children = categories.filter((c) => c.parent_id);
    return parents.map((p) => ({
      ...p,
      children: children
        .filter((c) => c.parent_id === p.id)
        .sort((a, b) => a.name.localeCompare(b.name)),
    }));
  }, [categories]);

  /* ---- Import ---------------------------------------------------- */
  const handleImport = async (file: File) => {
    setImporting(true);
    setImportProgress(0);
    setImportResult(null);
    setImportLogs([]);
    setImportError(null);
    setShowConsole(true);

    // Simulate progress during the network request
    const progressInterval = setInterval(() => {
      setImportProgress((p) => Math.min(p + 5, 85));
    }, 200);

    try {
      const result = await api.importFile(file);
      clearInterval(progressInterval);
      setImportProgress(100);
      setImportResult(result);
      if (result.log) setImportLogs(result.log);
      await load();
    } catch (err) {
      clearInterval(progressInterval);
      setImportProgress(0);
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleImport(file);
    e.target.value = "";
  };

  /* ---- Auto-scroll console --------------------------------------- */
  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [importLogs, importError, importResult]);

  /* ---- Uncategorized bulk ---------------------------------------- */
  const toggleUncategorized = (id: string) => {
    setSelectedUncategorized((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllUncategorized = () => {
    if (selectedUncategorized.size === uncategorized.length) {
      setSelectedUncategorized(new Set());
    } else {
      setSelectedUncategorized(new Set(uncategorized.map((t) => t.id)));
    }
  };

  const handleBulkCategorize = async () => {
    if (!bulkCategoryId || selectedUncategorized.size === 0) return;
    setBulkLoading(true);
    try {
      await api.bulkManualCategorize(Array.from(selectedUncategorized), bulkCategoryId);
      setSelectedUncategorized(new Set());
      setBulkCategoryId("");
      await load();
    } finally {
      setBulkLoading(false);
    }
  };

  const handleAiCategorize = async () => {
    const ids =
      selectedUncategorized.size > 0
        ? Array.from(selectedUncategorized)
        : uncategorized.map((t) => t.id);
    if (ids.length === 0) return;
    setAiLoading(true);
    try {
      await api.aiCategorize(ids);
      setSelectedUncategorized(new Set());
      await load();
    } finally {
      setAiLoading(false);
    }
  };

  /* ---- Inline editing -------------------------------------------- */
  const startEditing = (txn: TransactionItem) => {
    setEditingId(txn.id);
    setEditMerchant(txn.merchant);
    setEditNotes(txn.notes ?? "");
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditMerchant("");
    setEditNotes("");
  };

  const saveEditing = async () => {
    if (!editingId) return;
    setSavingEdit(true);
    try {
      await api.updateTransaction(editingId, {
        merchant: editMerchant,
        notes: editNotes || undefined,
      } as Partial<TransactionItem>);
      await load();
      cancelEditing();
    } finally {
      setSavingEdit(false);
    }
  };

  /* ---- Category cell --------------------------------------------- */
  const handleCategoryChange = async (txnId: string, categoryId: string) => {
    setCategoryLoading(txnId);
    setCategoryDropdownId(null);
    try {
      await api.manualCategorize(txnId, categoryId);
      await load();
    } finally {
      setCategoryLoading(null);
    }
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */
  return (
    <div className="space-y-6">
      {/* ---- Header ------------------------------------------------ */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Transactions</h1>

        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            onChange={onFileChange}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className={cn(
              "flex items-center gap-2 rounded-xl bg-primary px-4 h-11 text-[15px] font-medium text-primary-foreground",
              "active:scale-[0.98] cursor-pointer transition-all",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {importing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Import
          </button>
        </div>
      </div>

      {/* ---- Import Console ---------------------------------------- */}
      <AnimatePresence>
        {showConsole && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <GlassCard className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <h3 className="text-[15px] font-semibold">Import Console</h3>
                </div>
                <button
                  onClick={() => setShowConsole(false)}
                  className="rounded-xl p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all"
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>

              {/* Progress bar */}
              {importing && (
                <div className="space-y-2">
                  <div className="h-2 rounded-full bg-accent overflow-hidden">
                    <motion.div
                      className="h-full bg-primary rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${importProgress}%` }}
                      transition={{ ease: "easeOut" }}
                    />
                  </div>
                  <p className="text-[13px] text-muted-foreground">
                    Processing... {importProgress}%
                  </p>
                </div>
              )}

              {/* Result summary */}
              {importResult && (
                <div className="flex items-center gap-4 text-[13px]">
                  <span className="flex items-center gap-1 text-gain">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {importResult.imported} imported
                  </span>
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Tag className="h-3.5 w-3.5" />
                    {importResult.categorized} categorized
                  </span>
                  {importResult.skipped > 0 && (
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <AlertCircle className="h-3.5 w-3.5" />
                      {importResult.skipped} skipped
                    </span>
                  )}
                </div>
              )}

              {/* Error */}
              {importError && (
                <div className="flex items-center gap-2 text-[13px] text-loss">
                  <AlertCircle className="h-3.5 w-3.5" />
                  {importError}
                </div>
              )}

              {/* Log output */}
              <div
                ref={consoleRef}
                className="bg-card rounded-2xl p-4 max-h-48 overflow-y-auto font-mono text-[13px] space-y-1"
              >
                {importLogs.length === 0 && !importError && (
                  <p className="text-muted-foreground">
                    {importing ? "Waiting for server response..." : "No log entries."}
                  </p>
                )}
                {importLogs.map((entry, i) => (
                  <div key={i} className="text-muted-foreground">
                    <span className="text-foreground">{entry.msg}</span>
                    {entry.detail && (
                      <span className="ml-2 opacity-60">{entry.detail}</span>
                    )}
                  </div>
                ))}
              </div>
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Uncategorized Panel ----------------------------------- */}
      {uncategorized.length > 0 && (
        <GlassCard>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center h-8 w-8 rounded-xl bg-amber-500/10">
                <AlertCircle className="h-4 w-4 text-amber-500" />
              </div>
              <div>
                <h3 className="text-[15px] font-semibold">Uncategorized</h3>
                <p className="text-[13px] text-muted-foreground">
                  {uncategorized.length} transaction
                  {uncategorized.length !== 1 ? "s" : ""} need categorization
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Select all */}
              <button
                onClick={toggleAllUncategorized}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl px-3 h-9 text-[13px] font-medium",
                  "bg-accent hover:bg-accent/80 active:scale-[0.98] cursor-pointer transition-all",
                )}
              >
                <ListChecks className="h-3.5 w-3.5" />
                {selectedUncategorized.size === uncategorized.length
                  ? "Deselect All"
                  : "Select All"}
              </button>

              {/* Bulk category picker */}
              <select
                value={bulkCategoryId}
                onChange={(e) => setBulkCategoryId(e.target.value)}
                className="h-9 rounded-xl bg-accent px-3 text-[13px] border-none outline-none cursor-pointer"
              >
                <option value="">Category...</option>
                {groupedCategories.map((g) => (
                  <optgroup key={g.id} label={g.name}>
                    {g.children.length > 0 ? (
                      g.children.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))
                    ) : (
                      <option value={g.id}>{g.name}</option>
                    )}
                  </optgroup>
                ))}
              </select>

              <button
                onClick={handleBulkCategorize}
                disabled={!bulkCategoryId || selectedUncategorized.size === 0 || bulkLoading}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl px-3 h-9 text-[13px] font-medium",
                  "bg-primary text-primary-foreground active:scale-[0.98] cursor-pointer transition-all",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                )}
              >
                {bulkLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Tag className="h-3.5 w-3.5" />
                )}
                Apply
              </button>

              <button
                onClick={handleAiCategorize}
                disabled={aiLoading}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl px-4 h-9 text-[13px] font-medium",
                  "bg-chart-2 text-white active:scale-[0.98] cursor-pointer transition-all",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                {aiLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" />
                )}
                AI Categorize
                {selectedUncategorized.size > 0
                  ? ` (${selectedUncategorized.size})`
                  : ` (${uncategorized.length})`}
              </button>
            </div>
          </div>

          {/* Uncategorized pill previews */}
          <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto">
            {uncategorized.slice(0, 20).map((txn) => (
              <button
                key={txn.id}
                onClick={() => toggleUncategorized(txn.id)}
                className={cn(
                  "flex items-center gap-2 rounded-xl px-3 py-1.5 text-[13px] transition-all cursor-pointer",
                  "active:scale-[0.98]",
                  selectedUncategorized.has(txn.id)
                    ? "bg-primary/15 text-primary ring-1 ring-primary/30"
                    : "bg-accent hover:bg-accent/80",
                )}
              >
                <span className="truncate max-w-[140px]">{txn.merchant}</span>
                <span
                  className={cn(
                    "font-medium tabular-nums",
                    txn.amount >= 0 ? "text-gain" : "text-loss",
                  )}
                >
                  {formatCurrency(txn.amount, txn.currency)}
                </span>
              </button>
            ))}
            {uncategorized.length > 20 && (
              <span className="text-[13px] text-muted-foreground self-center ml-1">
                +{uncategorized.length - 20} more
              </span>
            )}
          </div>
        </GlassCard>
      )}

      {/* ---- Search + Table ---------------------------------------- */}
      <GlassCard className="space-y-4">
        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search merchant, description, category..."
            className={cn(
              "w-full h-11 rounded-xl bg-accent pl-10 pr-4 text-[15px] outline-none",
              "placeholder:text-muted-foreground/60 transition-all",
              "focus:ring-2 focus:ring-primary/30",
            )}
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 cursor-pointer"
            >
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          )}
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Empty state */}
        {!loading && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <ReceiptText className="h-16 w-16 text-muted-foreground/20 mb-4" />
            {transactions.length === 0 ? (
              <>
                <p className="text-[15px] font-medium text-muted-foreground">
                  No transactions yet
                </p>
                <p className="text-[13px] text-muted-foreground/60 mt-1">
                  Import a CSV, XML, or TSV file to get started
                </p>
              </>
            ) : (
              <>
                <p className="text-[15px] font-medium text-muted-foreground">
                  No matching transactions
                </p>
                <p className="text-[13px] text-muted-foreground/60 mt-1">
                  Try adjusting your search terms
                </p>
              </>
            )}
          </div>
        )}

        {/* Transaction table */}
        {!loading && filtered.length > 0 && (
          <>
            <div className="overflow-x-auto -mx-6 px-6">
              <table className="w-full text-[15px]">
                <thead>
                  <tr className="border-b border-border text-[13px] text-muted-foreground">
                    <th className="text-left font-medium pb-3 pr-4">Date</th>
                    <th className="text-left font-medium pb-3 pr-4">Merchant</th>
                    <th className="text-left font-medium pb-3 pr-4">Description</th>
                    <th className="text-left font-medium pb-3 pr-4">Category</th>
                    <th className="text-right font-medium pb-3 pr-4">Amount</th>
                    <th className="pb-3 w-10" />
                  </tr>
                </thead>
                <tbody>
                  {paginated.map((txn) => {
                    const isEditing = editingId === txn.id;
                    const isHighlighted = txn.id === urlHighlight;
                    const isIncome = txn.amount >= 0;

                    return (
                      <tr
                        key={txn.id}
                        ref={isHighlighted ? highlightRef : undefined}
                        className={cn(
                          "group border-b border-border/50 transition-colors hover:bg-accent/30",
                          isHighlighted && "bg-primary/5 ring-1 ring-primary/20",
                        )}
                      >
                        {/* Date */}
                        <td className="py-3 pr-4 whitespace-nowrap text-[13px] text-muted-foreground tabular-nums">
                          {formatDate(txn.date)}
                        </td>

                        {/* Merchant */}
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
                              <div
                                className={cn(
                                  "flex items-center justify-center h-7 w-7 rounded-lg shrink-0",
                                  isIncome ? "bg-emerald-500/10" : "bg-rose-500/10",
                                )}
                              >
                                {isIncome ? (
                                  <ArrowDownLeft className="h-3.5 w-3.5 text-emerald-500" />
                                ) : (
                                  <ArrowUpRight className="h-3.5 w-3.5 text-rose-500" />
                                )}
                              </div>
                              <span className="font-medium truncate max-w-[200px]">
                                {txn.merchant}
                              </span>
                            </div>
                          )}
                        </td>

                        {/* Notes / Description */}
                        <td className="py-3 pr-4">
                          {isEditing ? (
                            <input
                              value={editNotes}
                              onChange={(e) => setEditNotes(e.target.value)}
                              placeholder="Notes..."
                              className="h-9 w-full rounded-xl bg-accent px-3 text-[15px] outline-none placeholder:text-muted-foreground/40 focus:ring-2 focus:ring-primary/30"
                            />
                          ) : (
                            <span className="text-[13px] text-muted-foreground truncate block max-w-[220px]">
                              {txn.notes || "\u2014"}
                            </span>
                          )}
                        </td>

                        {/* Category */}
                        <td className="py-3 pr-4 relative">
                          {categoryLoading === txn.id ? (
                            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                          ) : (
                            <>
                              <button
                                onClick={() =>
                                  setCategoryDropdownId(
                                    categoryDropdownId === txn.id ? null : txn.id,
                                  )
                                }
                                className={cn(
                                  "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[13px] transition-all cursor-pointer",
                                  "active:scale-[0.98]",
                                  txn.category_name
                                    ? "bg-primary/10 text-primary hover:bg-primary/15"
                                    : "bg-accent text-muted-foreground hover:bg-accent/80",
                                )}
                              >
                                <Tag className="h-3 w-3" />
                                {txn.category_name ?? "Uncategorized"}
                              </button>
                              {txn.parent_category_name && txn.parent_category_name !== txn.category_name && (
                                <span className="block text-[11px] text-muted-foreground/60 mt-0.5 pl-1">
                                  {txn.parent_category_name}
                                </span>
                              )}
                            </>
                          )}

                          {/* Category dropdown */}
                          {categoryDropdownId === txn.id && (
                            <div
                              ref={dropdownRef}
                              className="absolute z-50 top-full left-0 mt-1 w-56 bg-popover rounded-2xl border border-border shadow-lg p-2 max-h-64 overflow-y-auto"
                            >
                              {groupedCategories.map((g) => (
                                <div key={g.id}>
                                  <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider px-2 pt-2 pb-1">
                                    {g.name}
                                  </div>
                                  {g.children.length > 0 ? (
                                    g.children.map((c) => (
                                      <button
                                        key={c.id}
                                        onClick={() => handleCategoryChange(txn.id, c.id)}
                                        className={cn(
                                          "w-full text-left px-2 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors",
                                          "hover:bg-accent active:scale-[0.98]",
                                          txn.category_id === c.id &&
                                            "bg-primary/10 text-primary",
                                        )}
                                      >
                                        {c.name}
                                      </button>
                                    ))
                                  ) : (
                                    <button
                                      onClick={() => handleCategoryChange(txn.id, g.id)}
                                      className={cn(
                                        "w-full text-left px-2 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors",
                                        "hover:bg-accent active:scale-[0.98]",
                                        txn.category_id === g.id &&
                                          "bg-primary/10 text-primary",
                                      )}
                                    >
                                      {g.name}
                                    </button>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>

                        {/* Amount */}
                        <td
                          className={cn(
                            "py-3 pr-4 text-right whitespace-nowrap font-semibold tabular-nums",
                            isIncome ? "text-gain" : "text-loss",
                          )}
                        >
                          {formatCurrency(txn.amount, txn.currency)}
                        </td>

                        {/* Edit button */}
                        <td className="py-3 text-right">
                          {isEditing ? (
                            <div className="flex items-center gap-1 justify-end">
                              <button
                                onClick={saveEditing}
                                disabled={savingEdit}
                                className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-gain"
                              >
                                {savingEdit ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Check className="h-4 w-4" />
                                )}
                              </button>
                              <button
                                onClick={cancelEditing}
                                className="rounded-lg p-1.5 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-loss"
                              >
                                <X className="h-4 w-4" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => startEditing(txn)}
                              className="rounded-lg p-1.5 opacity-0 group-hover:opacity-100 hover:bg-accent active:scale-[0.98] cursor-pointer transition-all text-muted-foreground"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between pt-2">
              <p className="text-[13px] text-muted-foreground">
                {filtered.length} transaction{filtered.length !== 1 ? "s" : ""}
                {debouncedSearch && " found"}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className={cn(
                    "flex items-center justify-center h-9 w-9 rounded-xl",
                    "bg-accent hover:bg-accent/80 active:scale-[0.98] cursor-pointer transition-all",
                    "disabled:opacity-40 disabled:cursor-not-allowed",
                  )}
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-[13px] text-muted-foreground tabular-nums min-w-[80px] text-center">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className={cn(
                    "flex items-center justify-center h-9 w-9 rounded-xl",
                    "bg-accent hover:bg-accent/80 active:scale-[0.98] cursor-pointer transition-all",
                    "disabled:opacity-40 disabled:cursor-not-allowed",
                  )}
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </GlassCard>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Exported page with Suspense boundary for useSearchParams           */
/* ------------------------------------------------------------------ */
export default function TransactionsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-32">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <TransactionsInner />
    </Suspense>
  );
}
