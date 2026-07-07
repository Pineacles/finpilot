"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { api, type ColumnMapping, type CsvPreview, type ImportProfile, type ImportResult, type Overview } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/format";
import { X, Table2, Loader2, AlertCircle, CheckCircle2, Save } from "lucide-react";

const DATE_FORMATS = [
  { value: "%d.%m.%Y", label: "DD.MM.YYYY (31.12.2026)" },
  { value: "%d.%m.%y", label: "DD.MM.YY (31.12.26)" },
  { value: "%Y-%m-%d", label: "YYYY-MM-DD (2026-12-31)" },
  { value: "%d/%m/%Y", label: "DD/MM/YYYY (31/12/2026)" },
  { value: "%m/%d/%Y", label: "MM/DD/YYYY (12/31/2026)" },
];

// Best-effort header-name guesses so the common case needs zero clicks.
const DATE_HINTS = ["date", "datum", "buchungsdatum", "valuta"];
const AMOUNT_HINTS = ["amount", "betrag", "sum", "value"];
const DEBIT_HINTS = ["debit", "belastung", "lastschrift", "ausgang"];
const CREDIT_HINTS = ["credit", "gutschrift", "eingang"];
const DESC_HINTS = ["description", "text", "details", "beschreibung", "purpose", "merchant", "avisierungstext"];

function guessColumn(columns: string[], hints: string[]): string {
  const lower = columns.map(c => c.toLowerCase());
  for (const hint of hints) {
    const idx = lower.findIndex(c => c.includes(hint));
    if (idx >= 0) return columns[idx];
  }
  return "";
}

interface CsvMapperModalProps {
  file: File;
  onClose: () => void;
  onImported: (result: ImportResult) => void;
}

export function CsvMapperModal({ file, onClose, onImported }: CsvMapperModalProps) {
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [accounts, setAccounts] = useState<Overview["accounts"]>([]);
  const [profiles, setProfiles] = useState<ImportProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [dateCol, setDateCol] = useState("");
  const [dateFormat, setDateFormat] = useState("%d.%m.%Y");
  const [amountMode, setAmountMode] = useState<"single" | "split">("single");
  const [amountCol, setAmountCol] = useState("");
  const [debitCol, setDebitCol] = useState("");
  const [creditCol, setCreditCol] = useState("");
  const [descriptionCol, setDescriptionCol] = useState("");
  const [decimalSeparator, setDecimalSeparator] = useState<"." | ",">(".");
  const [invertAmount, setInvertAmount] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [saveProfileName, setSaveProfileName] = useState("");

  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.csvPreview(file), api.overview(), api.importProfiles().catch(() => [])])
      .then(([p, overview, profs]) => {
        setPreview(p);
        setAccounts(overview.accounts);
        setProfiles(profs);
        setDateCol(guessColumn(p.columns, DATE_HINTS));
        setAmountCol(guessColumn(p.columns, AMOUNT_HINTS));
        setDebitCol(guessColumn(p.columns, DEBIT_HINTS));
        setCreditCol(guessColumn(p.columns, CREDIT_HINTS));
        setDescriptionCol(guessColumn(p.columns, DESC_HINTS));
        if (overview.accounts.length) setAccountId(overview.accounts[0].id);
      })
      .catch(err => setLoadError(err instanceof Error ? err.message : "Could not read file"))
      .finally(() => setLoading(false));
  }, [file]);

  const applyProfile = (profileId: string) => {
    const profile = profiles.find(p => p.id === profileId);
    if (!profile) return;
    const m = profile.mapping;
    setDateCol(m.date_col);
    setDateFormat(m.date_format);
    setDecimalSeparator(m.decimal_separator === "," ? "," : ".");
    setInvertAmount(m.invert_amount);
    if (m.debit_col || m.credit_col) {
      setAmountMode("split");
      setDebitCol(m.debit_col || "");
      setCreditCol(m.credit_col || "");
    } else {
      setAmountMode("single");
      setAmountCol(m.amount_col || "");
    }
    setDescriptionCol(m.description_col || "");
    if (profile.account_id) setAccountId(profile.account_id);
  };

  const mapping: ColumnMapping = useMemo(() => ({
    date_col: dateCol,
    amount_col: amountMode === "single" ? amountCol : undefined,
    debit_col: amountMode === "split" ? debitCol : undefined,
    credit_col: amountMode === "split" ? creditCol : undefined,
    description_col: descriptionCol || undefined,
    date_format: dateFormat,
    decimal_separator: decimalSeparator,
    invert_amount: invertAmount,
    currency: "CHF",
  }), [dateCol, amountMode, amountCol, debitCol, creditCol, descriptionCol, dateFormat, decimalSeparator, invertAmount]);

  const canSubmit = Boolean(
    dateCol && accountId &&
    (amountMode === "single" ? amountCol : (debitCol || creditCol))
  );

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setImporting(true);
    setError(null);
    try {
      const result = await api.csvMappedImport(file, accountId, mapping, true, saveProfileName || undefined);
      onImported(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] bg-background/95 backdrop-blur-sm"
    >
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-[900px] px-6 py-8 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-[22px] font-bold tracking-[-0.6px] flex items-center gap-2">
                <Table2 className="h-5 w-5" />
                Map columns
              </h2>
              <p className="text-[13px] text-muted-foreground mt-1">
                {file.name} isn&apos;t a recognized format — map its columns to import it anyway.
              </p>
            </div>
            <button
              onClick={onClose}
              disabled={importing}
              className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Reading file…
            </div>
          )}

          {loadError && (
            <div className="p-4 rounded-2xl bg-loss/10 text-loss text-[13px] flex items-center gap-2">
              <AlertCircle className="h-4 w-4" /> {loadError}
            </div>
          )}

          {preview && !loading && (
            <>
              {/* Saved profiles */}
              {profiles.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wide">
                    Use a saved profile
                  </label>
                  <select
                    onChange={e => e.target.value && applyProfile(e.target.value)}
                    defaultValue=""
                    className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
                  >
                    <option value="">— Select a saved mapping —</option>
                    {profiles.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Preview table */}
              <div className="rounded-2xl border border-border overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="bg-accent">
                      {preview.columns.map(col => (
                        <th key={col} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} className="border-t border-border">
                        {preview.columns.map(col => (
                          <td key={col} className="px-3 py-2 whitespace-nowrap text-muted-foreground">{row[col]}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Column mapping controls */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">Date column</label>
                  <ColumnSelect columns={preview.columns} value={dateCol} onChange={setDateCol} />
                </div>
                <div>
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">Date format</label>
                  <select
                    value={dateFormat}
                    onChange={e => setDateFormat(e.target.value)}
                    className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
                  >
                    {DATE_FORMATS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                  </select>
                </div>

                <div className="sm:col-span-2">
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">Amount columns</label>
                  <div className="flex gap-2 mb-2">
                    <button
                      type="button"
                      onClick={() => setAmountMode("single")}
                      className={cn("h-9 px-3 rounded-lg text-[12px] font-medium", amountMode === "single" ? "bg-primary text-primary-foreground" : "bg-accent")}
                    >
                      Single amount column
                    </button>
                    <button
                      type="button"
                      onClick={() => setAmountMode("split")}
                      className={cn("h-9 px-3 rounded-lg text-[12px] font-medium", amountMode === "split" ? "bg-primary text-primary-foreground" : "bg-accent")}
                    >
                      Separate debit/credit columns
                    </button>
                  </div>
                  {amountMode === "single" ? (
                    <ColumnSelect columns={preview.columns} value={amountCol} onChange={setAmountCol} />
                  ) : (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-[11px] text-muted-foreground mb-1">Debit (money out)</p>
                        <ColumnSelect columns={preview.columns} value={debitCol} onChange={setDebitCol} />
                      </div>
                      <div>
                        <p className="text-[11px] text-muted-foreground mb-1">Credit (money in)</p>
                        <ColumnSelect columns={preview.columns} value={creditCol} onChange={setCreditCol} />
                      </div>
                    </div>
                  )}
                </div>

                <div>
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">Description column</label>
                  <ColumnSelect columns={preview.columns} value={descriptionCol} onChange={setDescriptionCol} allowEmpty />
                </div>

                <div>
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">Decimal separator</label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setDecimalSeparator(".")}
                      className={cn("h-11 flex-1 rounded-xl text-[13px] font-medium", decimalSeparator === "." ? "bg-primary text-primary-foreground" : "bg-accent")}
                    >
                      1&apos;234.50
                    </button>
                    <button
                      type="button"
                      onClick={() => setDecimalSeparator(",")}
                      className={cn("h-11 flex-1 rounded-xl text-[13px] font-medium", decimalSeparator === "," ? "bg-primary text-primary-foreground" : "bg-accent")}
                    >
                      1&apos;234,50
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-6 sm:mt-0">
                  <button
                    type="button"
                    onClick={() => setInvertAmount(!invertAmount)}
                    className={cn("h-11 px-4 rounded-xl text-[13px] font-medium flex items-center gap-2", invertAmount ? "bg-primary text-primary-foreground" : "bg-accent")}
                  >
                    Invert amount sign
                  </button>
                </div>

                <div className="sm:col-span-2">
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">Target account</label>
                  <select
                    value={accountId}
                    onChange={e => setAccountId(e.target.value)}
                    className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
                  >
                    {accounts.map(a => (
                      <option key={a.id} value={a.id}>{a.name} ({a.type})</option>
                    ))}
                  </select>
                </div>

                <div className="sm:col-span-2">
                  <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                    Save as reusable profile (optional)
                  </label>
                  <Input
                    value={saveProfileName}
                    onChange={e => setSaveProfileName(e.target.value)}
                    placeholder="e.g. Cumulus Card Export"
                    className="rounded-xl h-11"
                  />
                </div>
              </div>

              {error && (
                <div className="p-3 rounded-xl bg-loss/10 text-loss text-[13px] flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" /> {error}
                </div>
              )}

              <button
                onClick={handleSubmit}
                disabled={!canSubmit || importing}
                className={cn(
                  "w-full h-12 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px]",
                  "active:scale-[0.98] cursor-pointer transition-all",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  "flex items-center justify-center gap-2",
                )}
              >
                {importing ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />Importing...</>
                ) : (
                  <><CheckCircle2 className="h-4 w-4" />Import with this mapping</>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function ColumnSelect({ columns, value, onChange, allowEmpty }: { columns: string[]; value: string; onChange: (v: string) => void; allowEmpty?: boolean }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
    >
      {allowEmpty && <option value="">— None —</option>}
      {!allowEmpty && !value && <option value="">— Select column —</option>}
      {columns.map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}
