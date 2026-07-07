"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api, Category, Overview, TransactionItem } from "@/lib/api";
import { GlassCard } from "@/components/glass-card";
import { ImportOverlay } from "@/components/transactions/import-overlay";
import { AddTransactionDialog } from "@/components/transactions/add-transaction-dialog";
import { UncategorizedPanel } from "@/components/transactions/uncategorized-panel";
import { TransactionFilters } from "@/components/transactions/transaction-filters";
import { TransactionsTable } from "@/components/transactions/transactions-table";
import {
  useTransactionsQuery, useCategoriesQuery, useOverviewQuery,
  useUpdateTransaction, useDeleteTransaction, useBulkDeleteTransactions,
} from "@/hooks/queries";

// Stable empty-array references so useMemo/useEffect deps below don't see a
// "new array" on every render while a query is still loading.
const EMPTY_TRANSACTIONS: TransactionItem[] = [];
const EMPTY_CATEGORIES: Category[] = [];
const EMPTY_ACCOUNTS: Overview["accounts"] = [];

function TransactionsInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();

  const urlSearch = searchParams.get("search") ?? "";
  const urlHighlight = searchParams.get("highlight") ?? "";

  const [search, setSearch] = useState(urlSearch);
  const [debouncedSearch, setDebouncedSearch] = useState(urlSearch);

  const transactionsQuery = useTransactionsQuery({ limit: 2000 });
  const categoriesQuery = useCategoriesQuery();
  const overviewQuery = useOverviewQuery();

  const updateTransaction = useUpdateTransaction();
  const deleteTransaction = useDeleteTransaction();
  const bulkDeleteTransactions = useBulkDeleteTransactions();

  const transactions = transactionsQuery.data ?? EMPTY_TRANSACTIONS;
  const categories = categoriesQuery.data ?? EMPTY_CATEGORIES;
  const accounts = overviewQuery.data?.accounts ?? EMPTY_ACCOUNTS;

  // Debounce search into the URL (shareable/bookmarkable + survives refresh)
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
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

  const uncategorized = useMemo(() => transactions.filter((t) => !t.category_id), [transactions]);

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["categories"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
  };

  const handleCategorize = async (txnId: string, categoryId: string) => {
    await api.manualCategorize(txnId, categoryId);
    refreshAll();
  };

  const loading = transactionsQuery.isLoading || categoriesQuery.isLoading;

  return (
    <div className="space-y-6">
      {/* Action bar */}
      <div className="flex items-center justify-end gap-3">
        <ImportOverlay onImported={refreshAll} />
        <AddTransactionDialog accounts={accounts} categories={categories} onCreated={refreshAll} />
      </div>

      {uncategorized.length > 0 && (
        <UncategorizedPanel uncategorized={uncategorized} categories={categories} onDone={refreshAll} />
      )}

      <GlassCard className="space-y-4">
        <TransactionFilters value={search} onChange={setSearch} />

        <TransactionsTable
          transactions={filtered}
          categories={categories}
          loading={loading}
          hasAnyTransactions={transactions.length > 0}
          searchActive={!!debouncedSearch}
          highlightId={urlHighlight || undefined}
          onUpdate={async (id, data) => { await updateTransaction.mutateAsync({ id, data }); }}
          onCategorize={handleCategorize}
          onDeleteOne={async (id) => { await deleteTransaction.mutateAsync(id); }}
          onBulkDelete={async (ids) => {
            const res = await bulkDeleteTransactions.mutateAsync(ids);
            return res.deleted;
          }}
        />
      </GlassCard>
    </div>
  );
}

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
