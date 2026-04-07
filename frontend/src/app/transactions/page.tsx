"use client";

import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { api, TransactionItem, Category, ImportResult, ImportLogEntry } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Search, Upload, CheckCircle2, AlertCircle, Brain, Tag, Loader2, Terminal, ChevronDown, ChevronUp, Pencil, X, Check } from "lucide-react";

const IMPORT_STEPS = [
  { label: "Uploading file", pct: 10 },
  { label: "Parsing transactions", pct: 25 },
  { label: "Matching merchants", pct: 50 },
  { label: "AI categorizing unknowns", pct: 75 },
  { label: "Saving to database", pct: 90 },
  { label: "Done", pct: 100 },
];

const PAGE_SIZE = 50;

// Build grouped options: Parent > Sub1, Sub2...
function buildCategoryOptions(categories: Category[]) {
  const parents = categories.filter((c) => !c.parent_id).sort((a, b) => a.name.localeCompare(b.name));
  const childMap: Record<string, Category[]> = {};
  for (const c of categories) {
    if (c.parent_id) {
      if (!childMap[c.parent_id]) childMap[c.parent_id] = [];
      childMap[c.parent_id].push(c);
    }
  }
  const opts: { value: string; label: string; isGroup?: boolean }[] = [];
  for (const p of parents) {
    const kids = (childMap[p.id] || []).sort((a, b) => a.name.localeCompare(b.name));
    if (kids.length > 0) {
      opts.push({ value: p.id, label: p.name, isGroup: true });
      for (const k of kids) opts.push({ value: k.id, label: `  ${k.name}` });
    } else {
      opts.push({ value: p.id, label: p.name });
    }
  }
  return opts;
}

// Inline category editor — only renders the <select> when clicked
function CategoryCell({ txn, categories, onCategorize }: {
  txn: TransactionItem;
  categories: Category[];
  onCategorize: (txnId: string, catId: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const options = buildCategoryOptions(categories);

  if (editing) {
    return (
      <select
        autoFocus
        className="rounded-md border bg-background px-2 py-1 text-xs w-40"
        value={txn.category_id || ""}
        onChange={(e) => { if (e.target.value) { onCategorize(txn.id, e.target.value); setEditing(false); } }}
        onBlur={() => setEditing(false)}
      >
        <option value="">--</option>
        {options.map((o) => (
          <option key={o.value} value={o.value} className={o.isGroup ? "font-bold" : ""}>{o.label}</option>
        ))}
      </select>
    );
  }

  return (
    <button onClick={() => setEditing(true)} className="text-left">
      {txn.category_name ? (
        <Badge variant="secondary" className="cursor-pointer hover:bg-accent">{txn.category_name}</Badge>
      ) : (
        <span className="text-xs text-muted-foreground hover:text-foreground cursor-pointer">+ Set category</span>
      )}
    </button>
  );
}

export default function TransactionsPage() {
  return (
    <Suspense>
      <TransactionsContent />
    </Suspense>
  );
}

function TransactionsContent() {
  const searchParams = useSearchParams();
  const highlightId = searchParams.get("highlight") || "";
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [filter, setFilter] = useState<"all" | "uncategorized">("all");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importStep, setImportStep] = useState(0);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState("");
  const [importLog, setImportLog] = useState<ImportLogEntry[]>([]);
  const [showConsole, setShowConsole] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiRunning, setAiRunning] = useState(false);
  const [aiResult, setAiResult] = useState<string | null>(null);
  const [editingTxn, setEditingTxn] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ merchant: "", notes: "" });
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    Promise.all([api.transactions({ limit: 2000 }), api.categories()])
      .then(([t, c]) => { setTransactions(t); setCategories(c); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Jump to highlighted transaction's page and scroll to it
  useEffect(() => {
    if (!highlightId || loading || transactions.length === 0) return;
    const idx = filtered.findIndex((t) => t.id === highlightId);
    if (idx >= 0) {
      const targetPage = Math.floor(idx / PAGE_SIZE) + 1;
      setPage(targetPage);
      setTimeout(() => {
        document.getElementById(`txn-${highlightId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
    }
  }, [highlightId, loading, transactions.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    setImportError("");
    setImportLog([]);
    setShowConsole(true);
    setImportStep(0);
    const stepTimer = setInterval(() => {
      setImportStep((prev) => (prev < IMPORT_STEPS.length - 2 ? prev + 1 : prev));
    }, 2000);
    try {
      const result = await api.importFile(file);
      clearInterval(stepTimer);
      setImportStep(IMPORT_STEPS.length - 1);
      setImportResult(result);
      if (result.log) setImportLog(result.log);
      load();
      setTimeout(() => setImporting(false), 3000);
    } catch (err) {
      clearInterval(stepTimer);
      setImportError(err instanceof Error ? err.message : "Import failed");
      setImporting(false);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleManualCategorize = async (txnId: string, categoryId: string) => {
    await api.manualCategorize(txnId, categoryId);
    load();
  };

  const handleBulkCategorize = async (categoryId: string) => {
    if (selected.size === 0) return;
    await api.bulkManualCategorize([...selected], categoryId);
    setSelected(new Set());
    load();
  };

  const handleAiCategorize = async () => {
    const ids = selected.size > 0 ? [...selected] : uncategorized.map((t) => t.id);
    if (ids.length === 0) return;
    setAiRunning(true);
    setAiResult(null);
    try {
      const result = await api.aiCategorize(ids, aiPrompt || undefined);
      setAiResult(`${result.categorized}/${result.sent} categorized by AI`);
      setSelected(new Set());
      setAiPrompt("");
      load();
    } catch {
      setAiResult("AI categorization failed");
    } finally {
      setAiRunning(false);
    }
  };

  const startEditTxn = (t: TransactionItem) => {
    setEditingTxn(t.id);
    setEditForm({ merchant: t.merchant, notes: t.notes || "" });
  };

  const saveEditTxn = async () => {
    if (!editingTxn) return;
    await api.updateTransaction(editingTxn, {
      merchant: editForm.merchant,
      notes: editForm.notes || undefined,
    } as Partial<TransactionItem>);
    setEditingTxn(null);
    load();
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const uncategorized = transactions.filter((t) => !t.category_name || t.category_name === "Other");

  const filtered = (() => {
    let list = filter === "uncategorized" ? uncategorized : transactions;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((t) =>
        t.merchant.toLowerCase().includes(q) ||
        (t.notes && t.notes.toLowerCase().includes(q)) ||
        (t.category_name && t.category_name.toLowerCase().includes(q))
      );
    }
    return list;
  })();

  // Pagination
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const displayed = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // Reset page when filter/search changes
  useEffect(() => { setPage(1); }, [filter, search]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Transactions</h1>
        <div className="flex items-center gap-3">
          {!importing && importError && (
            <div className="flex items-center gap-2 text-sm text-red-500">
              <AlertCircle className="h-4 w-4" />{importError}
            </div>
          )}
          <input ref={fileRef} type="file" accept=".csv,.xml,.tsv" className="hidden" onChange={handleImport} />
          <Button onClick={() => fileRef.current?.click()} disabled={importing} variant="outline">
            <Upload className="h-4 w-4 mr-2" />
            {importing ? "Importing..." : "Import Bank / Viseca"}
          </Button>
        </div>
      </div>

      {/* Import Progress */}
      {importing && (
        <Card>
          <CardContent className="py-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{IMPORT_STEPS[importStep].label}...</span>
                <span className="text-muted-foreground">{IMPORT_STEPS[importStep].pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-secondary overflow-hidden">
                <div className="h-full rounded-full bg-primary transition-all duration-700 ease-out" style={{ width: `${IMPORT_STEPS[importStep].pct}%` }} />
              </div>
              {importResult && (
                <div className="flex items-center gap-2 text-sm text-green-500 pt-1">
                  <CheckCircle2 className="h-4 w-4" />
                  {importResult.imported} imported, {importResult.categorized} categorized
                  {importResult.skipped > 0 && <span className="text-muted-foreground">({importResult.skipped} skipped)</span>}
                  {importResult.uncategorized > 0 && <span className="text-yellow-500">({importResult.uncategorized} uncategorized)</span>}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Import Console */}
      {importLog.length > 0 && (
        <Card className="border-zinc-700/50 bg-zinc-950">
          <CardHeader className="pb-2 cursor-pointer" onClick={() => setShowConsole(!showConsole)}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-zinc-300">
                <Terminal className="h-4 w-4" />
                <CardTitle className="text-sm font-mono">Import Log</CardTitle>
              </div>
              {showConsole ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
            </div>
          </CardHeader>
          {showConsole && (
            <CardContent className="pt-0">
              <div className="font-mono text-xs leading-relaxed max-h-64 overflow-y-auto space-y-0.5">
                {importLog.map((entry, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-zinc-600 select-none shrink-0">{String(i + 1).padStart(2, "0")}</span>
                    <span className={entry.msg.startsWith("  ") ? "text-zinc-400" : "text-green-400"}>{entry.msg}</span>
                    {entry.detail && <span className="text-zinc-600">{entry.detail}</span>}
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Uncategorized Panel */}
      {uncategorized.length > 0 && (
        <Card className="border-yellow-500/30">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Tag className="h-4 w-4 text-yellow-500" />
                <CardTitle className="text-base">{uncategorized.length} Uncategorized</CardTitle>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setFilter(filter === "uncategorized" ? "all" : "uncategorized")}>
                {filter === "uncategorized" ? "Show All" : "Show Only Uncategorized"}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <Button variant="outline" size="sm" onClick={() => setSelected(new Set(uncategorized.map((t) => t.id)))}>
                Select All ({uncategorized.length})
              </Button>
              {selected.size > 0 && (
                <>
                  <span className="text-xs text-muted-foreground">{selected.size} selected →</span>
                  <select className="rounded-md border bg-background px-2 py-1 text-sm" defaultValue="" onChange={(e) => { if (e.target.value) handleBulkCategorize(e.target.value); e.target.value = ""; }}>
                    <option value="">Set category...</option>
                    {buildCategoryOptions(categories).map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary shrink-0" />
              <Input placeholder="e.g. 'Person names = Transfer, Concordia = Insurance'" value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} className="text-sm" />
              <Button size="sm" onClick={handleAiCategorize} disabled={aiRunning}>
                {aiRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4 mr-1" />}
                {aiRunning ? "Running..." : `AI Categorize${selected.size > 0 ? ` (${selected.size})` : ""}`}
              </Button>
            </div>
            {aiResult && <p className="text-xs text-green-500 flex items-center gap-1"><CheckCircle2 className="h-3 w-3" />{aiResult}</p>}
          </CardContent>
        </Card>
      )}

      {/* Transactions Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>{filter === "uncategorized" ? "Uncategorized" : "All"} ({filtered.length})</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search merchant, description, category..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : displayed.length === 0 ? (
            <p className="text-sm text-muted-foreground">No transactions found.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      {filter === "uncategorized" && <th className="pb-2 w-8"></th>}
                      <th className="pb-2 font-medium">Date</th>
                      <th className="pb-2 font-medium">Merchant</th>
                      <th className="pb-2 font-medium">Description</th>
                      <th className="pb-2 font-medium">Category</th>
                      <th className="pb-2 font-medium text-right">Amount</th>
                      <th className="pb-2 w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayed.map((t) => (
                      editingTxn === t.id ? (
                        <tr key={t.id} className="border-b border-primary/30 bg-primary/5">
                          {filter === "uncategorized" && <td className="py-2"></td>}
                          <td className="py-2 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td>
                          <td className="py-2">
                            <Input
                              value={editForm.merchant}
                              onChange={(e) => setEditForm({ ...editForm, merchant: e.target.value })}
                              className="h-7 text-sm font-medium"
                            />
                          </td>
                          <td className="py-2">
                            <Input
                              value={editForm.notes}
                              onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                              className="h-7 text-xs"
                              placeholder="Description / notes"
                            />
                          </td>
                          <td className="py-2">
                            <CategoryCell txn={t} categories={categories} onCategorize={handleManualCategorize} />
                          </td>
                          <td className={`py-2 text-right font-medium whitespace-nowrap ${t.amount < 0 ? "text-red-500" : "text-green-500"}`}>
                            {formatCurrency(t.amount, t.currency)}
                          </td>
                          <td className="py-2">
                            <div className="flex gap-0.5">
                              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={saveEditTxn}>
                                <Check className="h-3 w-3 text-green-500" />
                              </Button>
                              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditingTxn(null)}>
                                <X className="h-3 w-3 text-muted-foreground" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        <tr key={t.id} id={`txn-${t.id}`} className={`border-b border-border/50 ${selected.has(t.id) ? "bg-primary/5" : ""} ${highlightId === t.id ? "bg-yellow-500/10 ring-1 ring-yellow-500/30" : ""}`}>
                          {filter === "uncategorized" && (
                            <td className="py-2"><input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} /></td>
                          )}
                          <td className="py-2 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td>
                          <td className="py-2 font-medium">{t.merchant}</td>
                          <td className="py-2 max-w-[250px]">
                            {t.notes ? (
                              <span className="text-xs text-muted-foreground truncate block" title={t.notes}>
                                {t.notes.split("|")[0].trim().substring(0, 60)}
                                {t.notes.split("|")[0].trim().length > 60 ? "..." : ""}
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">-</span>
                            )}
                          </td>
                          <td className="py-2">
                            <div className="flex flex-col gap-0.5">
                              {t.parent_category_name && (
                                <span className="text-[10px] text-muted-foreground leading-none">{t.parent_category_name}</span>
                              )}
                              <CategoryCell txn={t} categories={categories} onCategorize={handleManualCategorize} />
                            </div>
                          </td>
                          <td className={`py-2 text-right font-medium whitespace-nowrap ${t.amount < 0 ? "text-red-500" : "text-green-500"}`}>
                            {formatCurrency(t.amount, t.currency)}
                          </td>
                          <td className="py-2">
                            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => startEditTxn(t)}>
                              <Pencil className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          </td>
                        </tr>
                      )
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between pt-4">
                  <p className="text-xs text-muted-foreground">
                    Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
                  </p>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</Button>
                    {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                      let p: number;
                      if (totalPages <= 7) p = i + 1;
                      else if (page <= 4) p = i + 1;
                      else if (page >= totalPages - 3) p = totalPages - 6 + i;
                      else p = page - 3 + i;
                      return (
                        <Button key={p} variant={p === page ? "default" : "ghost"} size="sm" className="w-8 h-8 p-0" onClick={() => setPage(p)}>
                          {p}
                        </Button>
                      );
                    })}
                    <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
