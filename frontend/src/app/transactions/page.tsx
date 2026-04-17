"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { GlassCard } from "@/components/glass-card";
import { CategoryPill } from "@/components/category-pill";
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
/*  Constants                                                          */
/* ------------------------------------------------------------------ */
const PAGE_SIZE = 25;
const ACCEPTED_EXTENSIONS = ".csv,.xml,.tsv,.pdf";

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

  const [showImportPage, setShowImportPage] = useState(false);
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [importResults, setImportResults] = useState<{file: string; status: "pending"|"importing"|"done"|"error"; result?: ImportResult; error?: string}[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

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
  const [editApplyMerchant, setEditApplyMerchant] = useState(true);
  const [editApplyCategory, setEditApplyCategory] = useState(true);
  const [editDescFilter, setEditDescFilter] = useState("");
  const [editOriginalMerchant, setEditOriginalMerchant] = useState("");

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

  /* ---- Bulk Import (import page) -------------------------------- */
  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(f => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      return ext && ["csv", "xml", "tsv", "pdf"].includes(ext);
    });
    if (files.length) setImportFiles(prev => [...prev, ...files]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length) setImportFiles(prev => [...prev, ...files]);
    e.target.value = "";
  };

  const removeImportFile = (idx: number) => {
    setImportFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const startBulkImport = async () => {
    if (!importFiles.length) return;
    setBulkImporting(true);
    const results = importFiles.map(f => ({
      file: f.name,
      status: "pending" as const,
    }));
    setImportResults([...results]);

    for (let i = 0; i < importFiles.length; i++) {
      setImportResults(prev => prev.map((r, j) => j === i ? {...r, status: "importing" as const} : r));
      try {
        const result = await api.importFile(importFiles[i]);
        setImportResults(prev => prev.map((r, j) => j === i ? {...r, status: "done" as const, result} : r));
      } catch (err) {
        setImportResults(prev => prev.map((r, j) => j === i ? {...r, status: "error" as const, error: err instanceof Error ? err.message : "Import failed"} : r));
      }
    }

    setBulkImporting(false);
    setImportFiles([]);
    await load();
  };

  const closeImportPage = () => {
    setShowImportPage(false);
    setImportFiles([]);
    setImportResults([]);
    setBulkImporting(false);
    setIsDragging(false);
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

  // Count siblings: other transactions with the same merchant name
  const editSiblingCount = useMemo(() => {
    if (!editOriginalMerchant) return 0;
    return transactions.filter(
      (t) => t.merchant === editOriginalMerchant && t.id !== editingId,
    ).length;
  }, [editOriginalMerchant, editingId, transactions]);

  // Count how many siblings have distinct descriptions (to show description filter hint)
  const editDistinctDescriptions = useMemo(() => {
    if (!editOriginalMerchant) return [];
    const notes = new Set<string>();
    transactions
      .filter((t) => t.merchant === editOriginalMerchant)
      .forEach((t) => {
        if (t.notes) notes.add(t.notes.toLowerCase().split(/\s+/)[0]);
      });
    return Array.from(notes).slice(0, 10);
  }, [editOriginalMerchant, transactions]);

  // Count how many will be affected by current filter
  const editFilteredCount = useMemo(() => {
    if (!editOriginalMerchant || !editApplyMerchant) return 0;
    return transactions.filter((t) => {
      if (t.merchant !== editOriginalMerchant || t.id === editingId) return false;
      if (editDescFilter) {
        return (t.notes ?? "").toLowerCase().includes(editDescFilter.toLowerCase());
      }
      return true;
    }).length;
  }, [editOriginalMerchant, editingId, editApplyMerchant, editDescFilter, transactions]);

  const saveEditing = async () => {
    if (!editingId) return;
    setSavingEdit(true);
    try {
      await api.updateTransaction(editingId, {
        merchant: editMerchant,
        notes: editNotes || undefined,
        apply_merchant_to_all: editApplyMerchant,
        apply_category_to_all: editApplyCategory,
        description_filter: editDescFilter || undefined,
      } as any);
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
            onClick={() => setShowImportPage(true)}
            className={cn(
              "flex items-center gap-2 rounded-xl border border-border px-4 h-11 text-[15px] font-medium",
              "hover:bg-accent active:scale-[0.98] cursor-pointer transition-all",
            )}
          >
            <Upload className="h-4 w-4" />
            Import
          </button>
        </div>
      </div>

      {/* ---- Import Page Overlay ------------------------------------ */}
      <AnimatePresence>
        {showImportPage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm"
          >
            <div className="h-full overflow-y-auto">
              <div className="mx-auto max-w-[800px] px-6 py-8 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-bold tracking-tight">Import Files</h2>
                    <p className="text-[13px] text-muted-foreground mt-1">
                      Drag & drop bank statements or click to browse. Supports CSV, TSV, XML, and PDF.
                    </p>
                  </div>
                  <button
                    onClick={closeImportPage}
                    disabled={bulkImporting}
                    className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Drop Zone */}
                <div
                  ref={dropRef}
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleFileDrop}
                  onClick={() => {
                    const input = document.createElement("input");
                    input.type = "file";
                    input.accept = ACCEPTED_EXTENSIONS;
                    input.multiple = true;
                    input.onchange = (e) => {
                      const files = Array.from((e.target as HTMLInputElement).files || []);
                      if (files.length) setImportFiles(prev => [...prev, ...files]);
                    };
                    input.click();
                  }}
                  className={cn(
                    "border-2 border-dashed rounded-3xl p-12 text-center cursor-pointer transition-all duration-200",
                    isDragging
                      ? "border-primary bg-primary/5 scale-[1.02]"
                      : "border-border hover:border-primary/50 hover:bg-accent/50",
                  )}
                >
                  <Upload className={cn("h-12 w-12 mx-auto mb-4", isDragging ? "text-primary" : "text-muted-foreground/40")} strokeWidth={1.5} />
                  <p className="text-[15px] font-medium">
                    {isDragging ? "Drop files here" : "Drop files here or click to browse"}
                  </p>
                  <p className="text-[13px] text-muted-foreground mt-1">
                    Valiant CSV, PostFinance CSV/PDF, Viseca CSV, camt.053 XML
                  </p>
                </div>

                {/* Queued Files */}
                {importFiles.length > 0 && (
                  <div className="space-y-3">
                    <p className="text-[13px] font-medium text-muted-foreground">
                      {importFiles.length} file{importFiles.length !== 1 ? "s" : ""} queued
                    </p>
                    <div className="space-y-2">
                      {importFiles.map((f, i) => (
                        <div key={`${f.name}-${i}`} className="flex items-center justify-between p-3 rounded-2xl bg-accent">
                          <div className="flex items-center gap-3">
                            <FileText className="h-5 w-5 text-muted-foreground" />
                            <div>
                              <p className="text-[14px] font-medium">{f.name}</p>
                              <p className="text-[12px] text-muted-foreground">{(f.size / 1024).toFixed(1)} KB</p>
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); removeImportFile(i); }}
                            className="p-1.5 rounded-lg hover:bg-background cursor-pointer transition-colors"
                          >
                            <X className="h-4 w-4 text-muted-foreground" />
                          </button>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={startBulkImport}
                      disabled={bulkImporting}
                      className={cn(
                        "w-full h-12 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px]",
                        "active:scale-[0.98] cursor-pointer transition-all",
                        "disabled:opacity-50 disabled:cursor-not-allowed",
                        "flex items-center justify-center gap-2",
                      )}
                    >
                      {bulkImporting ? (
                        <><Loader2 className="h-4 w-4 animate-spin" />Importing...</>
                      ) : (
                        <><Upload className="h-4 w-4" />Import {importFiles.length} file{importFiles.length !== 1 ? "s" : ""}</>
                      )}
                    </button>
                  </div>
                )}

                {/* Results */}
                {importResults.length > 0 && (
                  <div className="space-y-3">
                    <p className="text-[13px] font-medium text-muted-foreground">Results</p>
                    <div className="space-y-2">
                      {importResults.map((r, i) => (
                        <div key={`result-${i}`} className="p-4 rounded-2xl border border-border space-y-2">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              {r.status === "pending" && <div className="h-4 w-4 rounded-full bg-muted" />}
                              {r.status === "importing" && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
                              {r.status === "done" && <CheckCircle2 className="h-4 w-4 text-gain" />}
                              {r.status === "error" && <AlertCircle className="h-4 w-4 text-loss" />}
                              <span className="text-[14px] font-medium">{r.file}</span>
                            </div>
                            <span className={cn("text-[12px] font-medium capitalize",
                              r.status === "done" ? "text-gain" : r.status === "error" ? "text-loss" : "text-muted-foreground",
                            )}>
                              {r.status}
                            </span>
                          </div>
                          {r.status === "done" && r.result && (
                            <div className="flex flex-wrap gap-4 text-[12px] text-muted-foreground">
                              <span>{r.result.imported} imported</span>
                              <span>{r.result.categorized} categorized</span>
                              {r.result.skipped > 0 && <span>{r.result.skipped} skipped</span>}
                            </div>
                          )}
                          {r.status === "error" && r.error && (
                            <p className="text-[12px] text-loss">{r.error}</p>
                          )}
                        </div>
                      ))}
                    </div>
                    {!bulkImporting && (
                      <button
                        onClick={closeImportPage}
                        className="w-full h-11 rounded-xl bg-accent text-[14px] font-medium hover:bg-muted transition-colors cursor-pointer"
                      >
                        Done — Back to Transactions
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

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
                      <React.Fragment key={txn.id}>
                      <tr
                        ref={isHighlighted ? highlightRef : undefined}
                        className={cn(
                          "group border-b border-border/50 transition-colors hover:bg-accent/50",
                          isHighlighted && "animate-highlight-pulse bg-yellow-400/10 ring-1 ring-yellow-400/40",
                          isEditing && "bg-accent/20 border-b-0",
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
                                  "flex items-center justify-center h-8 w-8 rounded-full shrink-0",
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
                                className="cursor-pointer active:scale-[0.98] transition-all"
                              >
                                <CategoryPill
                                  name={txn.category_name ?? "Uncategorized"}
                                />
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
                      {/* Scope controls row — only shown when editing and there are sibling transactions */}
                      {isEditing && editSiblingCount > 0 && (
                        <tr className="border-b border-border/50 bg-accent/10">
                          <td colSpan={6} className="px-4 py-3">
                            <div className="flex flex-wrap items-center gap-4 text-[13px]">
                              <span className="text-muted-foreground font-medium">
                                {editSiblingCount} other &quot;{editOriginalMerchant}&quot; transaction{editSiblingCount !== 1 ? "s" : ""}
                              </span>

                              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                                <input
                                  type="checkbox"
                                  checked={editApplyMerchant}
                                  onChange={(e) => setEditApplyMerchant(e.target.checked)}
                                  className="rounded accent-primary cursor-pointer"
                                />
                                <span>Rename all</span>
                              </label>

                              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                                <input
                                  type="checkbox"
                                  checked={editApplyCategory}
                                  onChange={(e) => setEditApplyCategory(e.target.checked)}
                                  className="rounded accent-primary cursor-pointer"
                                />
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
                                <span className={cn(
                                  "text-[12px] px-2 py-0.5 rounded-lg font-medium",
                                  editFilteredCount > 0
                                    ? "bg-primary/10 text-primary"
                                    : "bg-muted text-muted-foreground",
                                )}>
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
