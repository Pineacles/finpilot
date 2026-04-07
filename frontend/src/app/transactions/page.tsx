"use client";

import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { api, TransactionItem, Category, ImportResult, ImportLogEntry } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Search, Upload, CheckCircle2, AlertCircle, Brain, Tag, Loader2, Terminal, ChevronDown, ChevronUp, Pencil, X, Check } from "lucide-react";

const PAGE_SIZE = 50;

function GlassCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`glass bg-card rounded-3xl p-6 ${className}`}>{children}</div>;
}

function buildCategoryOptions(categories: Category[]) {
  const parents = categories.filter(c => !c.parent_id).sort((a, b) => a.name.localeCompare(b.name));
  const childMap: Record<string, Category[]> = {};
  for (const c of categories) { if (c.parent_id) { if (!childMap[c.parent_id]) childMap[c.parent_id] = []; childMap[c.parent_id].push(c); } }
  const opts: { value: string; label: string }[] = [];
  for (const p of parents) { const kids = (childMap[p.id] || []).sort((a, b) => a.name.localeCompare(b.name)); if (kids.length) { opts.push({ value: p.id, label: p.name }); for (const k of kids) opts.push({ value: k.id, label: `  ${k.name}` }); } else opts.push({ value: p.id, label: p.name }); }
  return opts;
}

function CategoryCell({ txn, categories, onCategorize }: { txn: TransactionItem; categories: Category[]; onCategorize: (id: string, catId: string) => void }) {
  const [editing, setEditing] = useState(false);
  const options = buildCategoryOptions(categories);
  if (editing) return <select autoFocus className="rounded-xl border-0 bg-accent px-2 py-1.5 text-[13px] w-40" value={txn.category_id || ""} onChange={e => { if (e.target.value) { onCategorize(txn.id, e.target.value); setEditing(false); } }} onBlur={() => setEditing(false)}><option value="">--</option>{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>;
  return <button onClick={() => setEditing(true)} className="text-left cursor-pointer">{txn.category_name ? <Badge variant="secondary" className="cursor-pointer hover:bg-accent rounded-lg">{txn.category_name}</Badge> : <span className="text-[13px] text-muted-foreground hover:text-foreground cursor-pointer">+ Set</span>}</button>;
}

const IMPORT_STEPS = [{ label: "Uploading", pct: 10 }, { label: "Parsing", pct: 25 }, { label: "Matching", pct: 50 }, { label: "AI categorizing", pct: 75 }, { label: "Saving", pct: 90 }, { label: "Done", pct: 100 }];

export default function TransactionsPage() { return <Suspense><TransactionsContent /></Suspense>; }

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

  const load = useCallback(() => { Promise.all([api.transactions({ limit: 2000 }), api.categories()]).then(([t, c]) => { setTransactions(t); setCategories(c); }).finally(() => setLoading(false)); }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => { if (!highlightId || loading || !transactions.length) return; const idx = filtered.findIndex(t => t.id === highlightId); if (idx >= 0) { setPage(Math.floor(idx / PAGE_SIZE) + 1); setTimeout(() => document.getElementById(`txn-${highlightId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 100); } }, [highlightId, loading, transactions.length]);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    setImporting(true); setImportResult(null); setImportError(""); setImportLog([]); setShowConsole(true); setImportStep(0);
    const timer = setInterval(() => setImportStep(prev => prev < IMPORT_STEPS.length - 2 ? prev + 1 : prev), 2000);
    try { const result = await api.importFile(file); clearInterval(timer); setImportStep(IMPORT_STEPS.length - 1); setImportResult(result); if (result.log) setImportLog(result.log); load(); setTimeout(() => setImporting(false), 3000); }
    catch (err) { clearInterval(timer); setImportError(err instanceof Error ? err.message : "Import failed"); setImporting(false); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  };

  const handleManualCategorize = async (txnId: string, categoryId: string) => { await api.manualCategorize(txnId, categoryId); load(); };
  const handleBulkCategorize = async (categoryId: string) => { if (!selected.size) return; await api.bulkManualCategorize([...selected], categoryId); setSelected(new Set()); load(); };
  const handleAiCategorize = async () => { const ids = selected.size > 0 ? [...selected] : uncategorized.map(t => t.id); if (!ids.length) return; setAiRunning(true); setAiResult(null); try { const r = await api.aiCategorize(ids, aiPrompt || undefined); setAiResult(`${r.categorized}/${r.sent} categorized`); setSelected(new Set()); setAiPrompt(""); load(); } catch { setAiResult("Failed"); } finally { setAiRunning(false); } };
  const saveEditTxn = async () => { if (!editingTxn) return; await api.updateTransaction(editingTxn, { merchant: editForm.merchant, notes: editForm.notes || undefined } as any); setEditingTxn(null); load(); };
  const toggleSelect = (id: string) => { const next = new Set(selected); if (next.has(id)) next.delete(id); else next.add(id); setSelected(next); };

  const uncategorized = transactions.filter(t => !t.category_name || t.category_name === "Other");
  const filtered = (() => { let list = filter === "uncategorized" ? uncategorized : transactions; if (search) { const q = search.toLowerCase(); list = list.filter(t => t.merchant.toLowerCase().includes(q) || (t.notes && t.notes.toLowerCase().includes(q)) || (t.category_name && t.category_name.toLowerCase().includes(q))); } return list; })();
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const displayed = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  useEffect(() => { setPage(1); }, [filter, search]);

  const catOptions = buildCategoryOptions(categories);

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">Transactions</h1>
        <div className="flex items-center gap-3">
          {!importing && importError && <div className="flex items-center gap-2 text-[13px] text-loss"><AlertCircle className="h-4 w-4" />{importError}</div>}
          <input ref={fileRef} type="file" accept=".csv,.xml,.tsv" className="hidden" onChange={handleImport} />
          <Button onClick={() => fileRef.current?.click()} disabled={importing} className="rounded-xl"><Upload className="h-4 w-4 mr-1.5" />{importing ? "Importing..." : "Import"}</Button>
        </div>
      </motion.div>

      {/* Import Progress */}
      {importing && (
        <GlassCard>
          <div className="space-y-3">
            <div className="flex items-center justify-between text-[14px]"><span className="font-medium">{IMPORT_STEPS[importStep].label}...</span><span className="text-muted-foreground">{IMPORT_STEPS[importStep].pct}%</span></div>
            <div className="h-2.5 rounded-full bg-secondary overflow-hidden"><motion.div initial={{ width: 0 }} animate={{ width: `${IMPORT_STEPS[importStep].pct}%` }} transition={{ duration: 0.7 }} className="h-full rounded-full bg-primary" /></div>
            {importResult && <div className="flex items-center gap-2 text-[13px] text-gain pt-1"><CheckCircle2 className="h-4 w-4" />{importResult.imported} imported, {importResult.categorized} categorized{importResult.skipped > 0 && <span className="text-muted-foreground">({importResult.skipped} skipped)</span>}</div>}
          </div>
        </GlassCard>
      )}

      {/* Console */}
      {importLog.length > 0 && (
        <GlassCard className="!p-0 overflow-hidden">
          <button onClick={() => setShowConsole(!showConsole)} className="flex items-center justify-between w-full px-6 py-3 cursor-pointer hover:bg-accent/50 transition-colors">
            <div className="flex items-center gap-2 text-[14px]"><Terminal className="h-4 w-4" /><span className="font-medium font-mono">Import Log</span></div>
            {showConsole ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
          </button>
          {showConsole && <div className="px-6 pb-4 font-mono text-[13px] leading-relaxed max-h-64 overflow-y-auto space-y-0.5">{importLog.map((entry, i) => <div key={i} className="flex gap-2"><span className="text-muted-foreground select-none shrink-0 w-6 text-right">{String(i + 1).padStart(2, "0")}</span><span className={entry.msg.startsWith("  ") ? "text-muted-foreground" : "text-gain"}>{entry.msg}</span>{entry.detail && <span className="text-muted-foreground/60">{entry.detail}</span>}</div>)}</div>}
        </GlassCard>
      )}

      {/* Uncategorized */}
      {uncategorized.length > 0 && (
        <GlassCard className="border-amber-500/20 border">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2"><Tag className="h-5 w-5 text-amber-500" /><h2 className="text-lg font-semibold">{uncategorized.length} Uncategorized</h2></div>
            <button onClick={() => setFilter(filter === "uncategorized" ? "all" : "uncategorized")} className="text-[13px] text-muted-foreground hover:text-foreground cursor-pointer">{filter === "uncategorized" ? "Show All" : "Show Only Uncategorized"}</button>
          </div>
          <div className="flex items-center gap-3 flex-wrap mb-3">
            <Button variant="outline" size="sm" onClick={() => setSelected(new Set(uncategorized.map(t => t.id)))} className="rounded-xl">Select All ({uncategorized.length})</Button>
            {selected.size > 0 && <><span className="text-[13px] text-muted-foreground">{selected.size} selected</span><select className="rounded-xl border-0 bg-accent px-3 py-2 text-[14px]" defaultValue="" onChange={e => { if (e.target.value) handleBulkCategorize(e.target.value); e.target.value = ""; }}><option value="">Set category...</option>{catOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></>}
          </div>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary shrink-0" />
            <Input placeholder="e.g. 'Person names = Transfer'" value={aiPrompt} onChange={e => setAiPrompt(e.target.value)} className="rounded-xl h-10" />
            <Button size="sm" onClick={handleAiCategorize} disabled={aiRunning} className="rounded-xl shrink-0">{aiRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4 mr-1" />}{aiRunning ? "Running..." : `AI Categorize${selected.size > 0 ? ` (${selected.size})` : ""}`}</Button>
          </div>
          {aiResult && <p className="text-[13px] text-gain flex items-center gap-1 mt-2"><CheckCircle2 className="h-3 w-3" />{aiResult}</p>}
        </GlassCard>
      )}

      {/* Transactions Table */}
      <GlassCard>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">{filter === "uncategorized" ? "Uncategorized" : "All"} ({filtered.length})</h2>
          <div className="relative w-72"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input placeholder="Search merchant, description, category..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9 rounded-xl h-10" /></div>
        </div>

        {loading ? <p className="text-muted-foreground">Loading...</p> : displayed.length === 0 ? <div className="text-center py-16"><Search className="h-12 w-12 text-muted-foreground/20 mx-auto mb-3" /><p className="text-muted-foreground">No transactions found.</p></div> : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-[14px]">
                <thead><tr className="border-b text-left text-muted-foreground text-[13px]">{filter === "uncategorized" && <th className="pb-3 w-8" />}<th className="pb-3 font-medium">Date</th><th className="pb-3 font-medium">Merchant</th><th className="pb-3 font-medium">Description</th><th className="pb-3 font-medium">Category</th><th className="pb-3 font-medium text-right">Amount</th><th className="pb-3 w-10" /></tr></thead>
                <tbody>
                  {displayed.map(t => editingTxn === t.id ? (
                    <tr key={t.id} className="border-b border-primary/20 bg-accent/50">
                      {filter === "uncategorized" && <td />}
                      <td className="py-3 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td>
                      <td className="py-3"><Input value={editForm.merchant} onChange={e => setEditForm({ ...editForm, merchant: e.target.value })} className="h-8 rounded-xl text-[14px]" /></td>
                      <td className="py-3"><Input value={editForm.notes} onChange={e => setEditForm({ ...editForm, notes: e.target.value })} className="h-8 rounded-xl text-[13px]" placeholder="Notes" /></td>
                      <td className="py-3"><CategoryCell txn={t} categories={categories} onCategorize={handleManualCategorize} /></td>
                      <td className={`py-3 text-right font-medium tabular-nums ${t.amount < 0 ? "text-loss" : "text-gain"}`}>{formatCurrency(t.amount, t.currency)}</td>
                      <td className="py-3"><div className="flex gap-0.5"><button className="cursor-pointer p-1" onClick={saveEditTxn}><Check className="h-4 w-4 text-gain" /></button><button className="cursor-pointer p-1" onClick={() => setEditingTxn(null)}><X className="h-4 w-4 text-muted-foreground" /></button></div></td>
                    </tr>
                  ) : (
                    <tr key={t.id} id={`txn-${t.id}`} className={`border-b border-border/50 hover:bg-accent/30 transition-colors ${selected.has(t.id) ? "bg-accent/50" : ""} ${highlightId === t.id ? "bg-primary/8 ring-1 ring-primary/20" : ""}`}>
                      {filter === "uncategorized" && <td className="py-3"><input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} className="rounded cursor-pointer" /></td>}
                      <td className="py-3 text-muted-foreground whitespace-nowrap">{formatDate(t.date)}</td>
                      <td className="py-3 font-medium">{t.merchant}</td>
                      <td className="py-3 max-w-[250px]">{t.notes ? <span className="text-[13px] text-muted-foreground truncate block" title={t.notes}>{t.notes.split("|")[0].trim().substring(0, 60)}{t.notes.split("|")[0].trim().length > 60 ? "..." : ""}</span> : <span className="text-[13px] text-muted-foreground">-</span>}</td>
                      <td className="py-3"><div className="flex flex-col gap-0.5">{t.parent_category_name && <span className="text-[11px] text-muted-foreground leading-none">{t.parent_category_name}</span>}<CategoryCell txn={t} categories={categories} onCategorize={handleManualCategorize} /></div></td>
                      <td className={`py-3 text-right font-medium tabular-nums whitespace-nowrap ${t.amount < 0 ? "text-loss" : "text-gain"}`}>{formatCurrency(t.amount, t.currency)}</td>
                      <td className="py-3"><button className="cursor-pointer p-1 opacity-0 group-hover:opacity-100" onClick={() => { setEditingTxn(t.id); setEditForm({ merchant: t.merchant, notes: t.notes || "" }); }}><Pencil className="h-3.5 w-3.5 text-muted-foreground" /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-5">
                <p className="text-[13px] text-muted-foreground">Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}</p>
                <div className="flex items-center gap-1">
                  <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-3 py-1.5 rounded-lg text-[13px] font-medium disabled:opacity-30 hover:bg-accent cursor-pointer transition-colors">Prev</button>
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => { let p: number; if (totalPages <= 7) p = i + 1; else if (page <= 4) p = i + 1; else if (page >= totalPages - 3) p = totalPages - 6 + i; else p = page - 3 + i; return <button key={p} onClick={() => setPage(p)} className={`w-8 h-8 rounded-lg text-[13px] font-medium cursor-pointer transition-colors ${p === page ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{p}</button>; })}
                  <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-3 py-1.5 rounded-lg text-[13px] font-medium disabled:opacity-30 hover:bg-accent cursor-pointer transition-colors">Next</button>
                </div>
              </div>
            )}
          </>
        )}
      </GlassCard>
    </div>
  );
}
