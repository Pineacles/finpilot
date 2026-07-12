"use client";

/**
 * TanStack Query hooks for the pages touched in this phase (transactions,
 * merchants, dashboard/overview, recurring, settings, categories). Other
 * pages (portfolio, goals, stats, budgets) keep their existing
 * useState/useEffect data loading; not refactored this phase.
 *
 * Each mutation invalidates the query keys it can affect so pages using
 * these hooks stay in sync after a create/update/delete without manual
 * refetch plumbing.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  Category,
  CreateRecurringExpense,
  CreateTransaction,
  MerchantRule,
  Overview,
  RecurringExpense,
  RecurringSuggestion,
  TransactionItem,
} from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Query keys                                                         */
/* ------------------------------------------------------------------ */
export const queryKeys = {
  transactions: (params?: Record<string, unknown>) => ["transactions", params ?? {}] as const,
  categories: () => ["categories"] as const,
  overview: () => ["overview"] as const,
  merchants: () => ["merchants"] as const,
  recurring: () => ["recurring"] as const,
  recurringDetected: () => ["recurring-detected"] as const,
  settings: () => ["settings"] as const,
};

/* ------------------------------------------------------------------ */
/*  Transactions                                                       */
/* ------------------------------------------------------------------ */
export function useTransactionsQuery(params?: { limit?: number; offset?: number; category_id?: string; search?: string }) {
  return useQuery({
    queryKey: queryKeys.transactions(params),
    queryFn: () => api.transactions(params),
  });
}

export function useCreateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateTransaction) => api.createTransaction(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview() });
      qc.invalidateQueries({ queryKey: queryKeys.recurringDetected() });
    },
  });
}

export function useUpdateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TransactionItem> & { apply_merchant_to_all?: boolean; apply_category_to_all?: boolean; description_filter?: string } }) =>
      api.updateTransaction(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview() });
      qc.invalidateQueries({ queryKey: queryKeys.merchants() });
    },
  });
}

export function useDeleteTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteTransaction(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview() });
    },
  });
}

export function useBulkDeleteTransactions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => api.bulkDeleteTransactions(ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: queryKeys.overview() });
    },
  });
}

/* ------------------------------------------------------------------ */
/*  Categories                                                          */
/* ------------------------------------------------------------------ */
export function useCategoriesQuery() {
  return useQuery({ queryKey: queryKeys.categories(), queryFn: () => api.categories() });
}

/* ------------------------------------------------------------------ */
/*  Dashboard overview (net worth, accounts, recent txns, budget health) */
/* ------------------------------------------------------------------ */
export function useOverviewQuery() {
  return useQuery({ queryKey: queryKeys.overview(), queryFn: () => api.overview() });
}

/* ------------------------------------------------------------------ */
/*  Merchants (auto-categorization rules)                               */
/* ------------------------------------------------------------------ */
export function useMerchantsQuery() {
  return useQuery({ queryKey: queryKeys.merchants(), queryFn: () => api.merchants() });
}

export function useCreateMerchant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; patterns: string; default_category_id?: string }) => api.createMerchant(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.merchants() }),
  });
}

export function useUpdateMerchant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; patterns?: string; default_category_id?: string } }) =>
      api.updateMerchant(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.merchants() }),
  });
}

export function useDeleteMerchant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteMerchant(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.merchants() }),
  });
}

/* ------------------------------------------------------------------ */
/*  Recurring expenses + auto-detected suggestions                     */
/* ------------------------------------------------------------------ */
export function useRecurringQuery() {
  return useQuery({ queryKey: queryKeys.recurring(), queryFn: () => api.recurring() });
}

export function useRecurringDetectedQuery() {
  return useQuery({ queryKey: queryKeys.recurringDetected(), queryFn: () => api.detectedRecurring() });
}

function invalidateRecurring(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: queryKeys.recurring() });
  qc.invalidateQueries({ queryKey: queryKeys.recurringDetected() });
}

export function useCreateRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRecurringExpense) => api.createRecurring(data),
    onSuccess: () => invalidateRecurring(qc),
  });
}

export function useDeleteRecurring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteRecurring(id),
    onSuccess: () => invalidateRecurring(qc),
  });
}

/* ------------------------------------------------------------------ */
/*  Settings (generic k/v store, also backs dashboard layout & the      */
/*  dismissed-suggestions list)                                        */
/* ------------------------------------------------------------------ */
export function useSettingsQuery() {
  return useQuery({ queryKey: queryKeys.settings(), queryFn: () => api.getSettings() });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (settings: Record<string, string>) => api.updateSettings(settings),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.settings() }),
  });
}

// Re-exported for convenience so callers only need one import.
export type { Category, MerchantRule, Overview, RecurringExpense, RecurringSuggestion, TransactionItem };
