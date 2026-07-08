"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { api, ImportResult } from "@/lib/api";
import { cn } from "@/lib/format";
import { CsvMapperModal } from "@/components/csv-mapper-modal";
import {
  Upload, X, FileText, AlertCircle, CheckCircle2, Loader2,
} from "lucide-react";

const ACCEPTED_EXTENSIONS = ".csv,.xml,.tsv,.pdf";

interface ImportOverlayProps {
  /** Called after any import (single or bulk) completes so the caller can reload its transaction list. */
  onImported: () => void | Promise<void>;
}

/** "Import" trigger button + full-screen drag & drop overlay (bulk import
 * with per-file progress) + the generic CSV column-mapper fallback for
 * unrecognized formats. Self-contained: owns all of its own show/hide
 * state, the caller only needs to react to `onImported` to refresh its
 * transaction list. */
export function ImportOverlay({ onImported }: ImportOverlayProps) {
  const [showImportPage, setShowImportPage] = useState(false);
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [importResults, setImportResults] = useState<{ file: string; status: "pending" | "importing" | "done" | "error"; result?: ImportResult; error?: string; fileObj?: File }[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [bulkImporting, setBulkImporting] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

  // Generic CSV column-mapper (fallback for unrecognized formats)
  const [mapperFile, setMapperFile] = useState<File | null>(null);

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      return ext && ["csv", "xml", "tsv", "pdf"].includes(ext);
    });
    if (files.length) setImportFiles((prev) => [...prev, ...files]);
  };

  const removeImportFile = (idx: number) => {
    setImportFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const startBulkImport = async () => {
    if (!importFiles.length) return;
    setBulkImporting(true);
    const results = importFiles.map((f) => ({ file: f.name, status: "pending" as const, fileObj: f }));
    setImportResults([...results]);

    for (let i = 0; i < importFiles.length; i++) {
      setImportResults((prev) => prev.map((r, j) => (j === i ? { ...r, status: "importing" as const } : r)));
      try {
        const result = await api.importFile(importFiles[i]);
        setImportResults((prev) => prev.map((r, j) => (j === i ? { ...r, status: "done" as const, result } : r)));
      } catch (err) {
        setImportResults((prev) => prev.map((r, j) => (j === i ? { ...r, status: "error" as const, error: err instanceof Error ? err.message : "Import failed" } : r)));
      }
    }

    setBulkImporting(false);
    setImportFiles([]);
    await onImported();
  };

  const closeImportPage = () => {
    setShowImportPage(false);
    setImportFiles([]);
    setImportResults([]);
    setBulkImporting(false);
    setIsDragging(false);
  };

  const handleMapperImported = async (result: ImportResult) => {
    const importedFile = mapperFile;
    setMapperFile(null);
    setImportResults((prev) => prev.map((r) => (r.fileObj === importedFile ? { ...r, status: "done" as const, result } : r)));
    await onImported();
  };

  return (
    <>
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
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-[24px] font-bold tracking-[-0.6px]">Import Files</h2>
                    <p className="text-[13px] text-muted-foreground mt-1">
                      Drag &amp; drop bank statements or click to browse. Supports CSV, TSV, XML, and PDF.
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
                      if (files.length) setImportFiles((prev) => [...prev, ...files]);
                    };
                    input.click();
                  }}
                  className={cn(
                    "border-2 border-dashed rounded-3xl p-12 text-center cursor-pointer transition-all duration-200",
                    isDragging ? "border-primary bg-primary/5 scale-[1.02]" : "border-border hover:border-primary/50 hover:bg-accent/50",
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
                            <div className="space-y-2">
                              <p className="text-[12px] text-loss">{r.error}</p>
                              {r.fileObj && (
                                <button
                                  onClick={() => setMapperFile(r.fileObj!)}
                                  className="text-[12px] font-medium text-primary hover:underline cursor-pointer"
                                >
                                  Map columns manually →
                                </button>
                              )}
                            </div>
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

      {/* ---- Generic CSV column-mapper (unrecognized formats) ------- */}
      <AnimatePresence>
        {mapperFile && (
          <CsvMapperModal file={mapperFile} onClose={() => setMapperFile(null)} onImported={handleMapperImported} />
        )}
      </AnimatePresence>
    </>
  );
}
