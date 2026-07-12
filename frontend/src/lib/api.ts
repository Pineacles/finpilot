// All API calls go through the Next.js proxy at /api/* (same origin)
// The proxy forwards to the backend at localhost:8001

// Import all types for use within this file.
// They are also re-exported at the bottom so callers can import from '@/lib/api'.
import type {
  Overview, PortfolioSummary, PortfolioSnapshot, ValueTimelinePoint, Trade,
  StockTransaction, PublicPortfolio, TransactionItem,
  CreateTransaction, Category, Budget, CreateBudget, SavingsGoal, CreateGoal,
  Milestone, CreateMilestone, MerchantRule, ImportResult, MonthlyStats,
  YearlyStats, SyncStatus, BrokerList,
  BrokerStatus, BrokerAccount, SaxoSyncResult, SaxoSubPortfolio,
  SymbolClassification, AssetType, WatchlistItem,
  CreditCardAccount, ColumnMapping, CsvPreview, ImportProfile,
  RecurringExpense, CreateRecurringExpense, RecurringSuggestion,
} from "@/lib/types";

// Structured 422 detail from a currency mismatch on POST .../trade — see
// backend/app/services/portfolio_service.py CurrencyMismatchError.
export interface CurrencyMismatchDetail {
  error: "currency_mismatch";
  message: string;
  ticker: string;
  user_currency: string;
  quote_currency: string;
  suggested_ticker: string | null;
}

// Thrown by request() on any non-2xx response. `detail` preserves the raw
// (possibly structured) FastAPI error body — plain string errors just have
// message === detail, but callers that need to render a "use X instead"
// confirm button (currency mismatch) inspect `.detail` directly instead of
// re-parsing `.message`.
export class ApiError extends Error {
  detail: unknown;
  constructor(message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401 || res.status === 403) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      localStorage.removeItem("token");
      localStorage.removeItem("refreshToken");
      document.cookie = "token=; path=/; max-age=0";
      // Prevent multiple concurrent redirects
      const win = window as Window & { __redirecting?: boolean };
      if (!win.__redirecting) {
        win.__redirecting = true;
        window.location.href = "/login";
      }
    }
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message: unknown }).message)
        : res.statusText;
    throw new ApiError(message, detail);
  }

  return res.json();
}

export const api = {
  // Auth
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  // Dashboard
  overview: () => request<Overview>("/api/dashboard/overview"),
  portfolio: () => request<PortfolioSummary>("/api/dashboard/portfolio"),
  setAccountBalance: (accountId: string, balance: number) =>
    request<{ status: string }>(`/api/dashboard/accounts/${accountId}/set-balance`, {
      method: "POST",
      body: JSON.stringify({ balance }),
    }),
  portfolioHistory: (days = 90) => request<PortfolioSnapshot[]>(`/api/dashboard/portfolio/history?days=${days}`),
  portfolioValueTimeline: () => request<ValueTimelinePoint[]>("/api/dashboard/portfolio/value-timeline"),
  trade: (data: { symbol: string; type: string; quantity: number; price?: number; currency?: string; date?: string; fees?: number; deduct_from_cash?: boolean; confirm_currency?: boolean }) =>
    request<{ status: string; cash_balance?: number; symbol?: string; type?: string; quantity?: number; price?: number; currency?: string }>("/api/dashboard/portfolio/trade", { method: "POST", body: JSON.stringify(data) }),
  trades: (symbol?: string) =>
    request<Trade[]>(`/api/dashboard/portfolio/trades${symbol ? `?symbol=${symbol}` : ""}`),
  updatePosition: (id: string, data: { quantity?: number; avg_cost_price?: number }) =>
    request<{ status: string }>(`/api/dashboard/portfolio/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePosition: (id: string) =>
    request<{ status: string }>(`/api/dashboard/portfolio/${id}`, { method: "DELETE" }),
  priceChart: (ticker: string, range = "1y") =>
    request<{ ticker: string; range: string; data: { date: string; close: number }[] }>(`/api/dashboard/portfolio/chart/${ticker}?range=${range}`),
  livePrices: () =>
    request<Record<string, { price: number; change: number; change_pct: number }>>("/api/dashboard/portfolio/live-prices"),
  stockTransactions: (symbol?: string) =>
    request<StockTransaction[]>(`/api/dashboard/portfolio/transactions${symbol ? `?symbol=${symbol}` : ""}`),

  // Public sharing
  publicPortfolioStatus: () => request<{ enabled: boolean; token: string | null }>("/api/dashboard/portfolio/public/status"),
  publicPortfolioToggle: () => request<{ enabled: boolean; token: string | null }>("/api/dashboard/portfolio/public/toggle", { method: "POST" }),
  publicPortfolio: (token: string) =>
    fetch(`/api/public/portfolio/${token}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<PublicPortfolio>; }),
  publicChart: (token: string, ticker: string, range = "1y") =>
    fetch(`/api/public/portfolio/${token}/chart/${ticker}?range=${range}`).then(r => { if (!r.ok) throw new Error("No data"); return r.json() as Promise<{ ticker: string; range: string; data: { date: string; close: number }[] }>; }),
  publicTrades: (token: string, symbol?: string) =>
    fetch(`/api/public/portfolio/${token}/trades${symbol ? `?symbol=${symbol}` : ""}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<Trade[]>; }),
  publicPortfolioHistory: (token: string, days = 365) =>
    fetch(`/api/public/portfolio/${token}/history?days=${days}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<PortfolioSnapshot[]>; }),
  publicValueTimeline: (token: string) =>
    fetch(`/api/public/portfolio/${token}/value-timeline`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<ValueTimelinePoint[]>; }),
  publicLivePrices: (token: string) =>
    fetch(`/api/public/portfolio/${token}/live-prices`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<Record<string, { price: number; change: number; change_pct: number }>>; }),

  // Transactions
  transactions: (params?: { category_id?: string; from_date?: string; to_date?: string; search?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<TransactionItem[]>(`/api/dashboard/transactions?${qs}`);
  },
  createTransaction: (data: CreateTransaction) =>
    request<TransactionItem>("/api/dashboard/transactions", { method: "POST", body: JSON.stringify(data) }),
  updateTransaction: (id: string, data: Partial<TransactionItem> & { apply_merchant_to_all?: boolean; apply_category_to_all?: boolean; description_filter?: string }) =>
    request<TransactionItem>(`/api/dashboard/transactions/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteTransaction: (id: string) =>
    request<{ status: string; id: string }>(`/api/dashboard/transactions/${id}`, { method: "DELETE" }),
  bulkDeleteTransactions: (ids: string[]) =>
    request<{ status: string; deleted: number }>("/api/dashboard/transactions/bulk-delete", {
      method: "POST", body: JSON.stringify({ transaction_ids: ids }),
    }),

  // Categories
  categories: () => request<Category[]>("/api/dashboard/categories"),
  createCategory: (data: { name: string; type: string; parent_id?: string }) =>
    request<Category>("/api/dashboard/categories", { method: "POST", body: JSON.stringify(data) }),

  // Budgets
  budgets: () => request<Budget[]>("/api/dashboard/budgets"),
  createBudget: (data: CreateBudget) =>
    request<Budget>("/api/dashboard/budgets", { method: "POST", body: JSON.stringify(data) }),
  deleteBudget: (id: string) =>
    request<void>(`/api/dashboard/budgets/${id}`, { method: "DELETE" }),

  // Goals
  goals: () => request<SavingsGoal[]>("/api/dashboard/goals"),
  createGoal: (data: CreateGoal) =>
    request<SavingsGoal>("/api/dashboard/goals", { method: "POST", body: JSON.stringify(data) }),
  updateGoal: (id: string, data: Partial<SavingsGoal>) =>
    request<SavingsGoal>(`/api/dashboard/goals/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  // Milestones
  milestones: () => request<Milestone[]>("/api/dashboard/milestones"),
  createMilestone: (data: CreateMilestone) =>
    request<Milestone>("/api/dashboard/milestones", { method: "POST", body: JSON.stringify(data) }),

  // Recurring expenses (bills/subscriptions) + auto-detected suggestions
  recurring: () => request<RecurringExpense[]>("/api/dashboard/recurring"),
  detectedRecurring: () => request<RecurringSuggestion[]>("/api/dashboard/recurring/detected"),
  createRecurring: (data: CreateRecurringExpense) =>
    request<RecurringExpense>("/api/dashboard/recurring", { method: "POST", body: JSON.stringify(data) }),
  deleteRecurring: (id: string) =>
    request<{ status: string; id: string }>(`/api/dashboard/recurring/${id}`, { method: "DELETE" }),

  // Merchants (categorization rules)
  merchants: () => request<MerchantRule[]>("/api/dashboard/merchants"),
  createMerchant: (data: { name: string; patterns: string; default_category_id?: string }) =>
    request<MerchantRule>("/api/dashboard/merchants", { method: "POST", body: JSON.stringify(data) }),
  updateMerchant: (id: string, data: { name?: string; patterns?: string; default_category_id?: string }) =>
    request<MerchantRule>(`/api/dashboard/merchants/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteMerchant: (id: string) =>
    request<void>(`/api/dashboard/merchants/${id}`, { method: "DELETE" }),

  // Categorize
  manualCategorize: (transactionId: string, categoryId: string) =>
    request<{ status: string }>("/api/dashboard/categorize/manual", {
      method: "POST", body: JSON.stringify({ transaction_id: transactionId, category_id: categoryId }),
    }),
  bulkManualCategorize: (transactionIds: string[], categoryId: string) =>
    request<{ status: string; updated: number }>("/api/dashboard/categorize/bulk-manual", {
      method: "POST", body: JSON.stringify({ transaction_ids: transactionIds, category_id: categoryId }),
    }),
  aiCategorize: (transactionIds: string[], customPrompt?: string) =>
    request<{ status: string; sent: number; categorized: number; results: { id: string; category_id: string | null; category_name: string; confidence: number }[] }>("/api/dashboard/categorize/ai", {
      method: "POST", body: JSON.stringify({ transaction_ids: transactionIds, custom_prompt: customPrompt }),
    }),

  // Import
  importFile: async (file: File, useAi = true) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const form = new FormData();
    form.append("file", file);
    form.append("use_ai", String(useAi));
    const res = await fetch("/api/import/csv", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Import failed");
    }
    return res.json() as Promise<ImportResult>;
  },

  // Generic CSV column-mapper (fallback for unrecognized formats, e.g. Cumulus exports)
  csvPreview: async (file: File) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/import/csv/preview", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Preview failed");
    }
    return res.json() as Promise<CsvPreview>;
  },
  csvMappedImport: async (
    file: File, accountId: string, mapping: ColumnMapping, useAi = true, saveAsProfileName?: string,
  ) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const form = new FormData();
    form.append("file", file);
    form.append("account_id", accountId);
    form.append("mapping", JSON.stringify(mapping));
    form.append("use_ai", String(useAi));
    if (saveAsProfileName) form.append("save_as_profile_name", saveAsProfileName);
    const res = await fetch("/api/import/csv/mapped", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Import failed");
    }
    return res.json() as Promise<ImportResult>;
  },
  importProfiles: () => request<ImportProfile[]>("/api/import/profiles"),
  createImportProfile: (data: { name: string; account_id?: string; mapping: ColumnMapping }) =>
    request<ImportProfile>("/api/import/profiles", { method: "POST", body: JSON.stringify(data) }),
  deleteImportProfile: (id: string) =>
    request<{ status: string; id: string }>(`/api/import/profiles/${id}`, { method: "DELETE" }),

  // Credit-card settlement patterns (Cumulus/Cembra auto-reset config)
  creditCardAccounts: () => request<CreditCardAccount[]>("/api/dashboard/accounts/credit-cards"),
  updateSettlementPatterns: (accountId: string, patterns: string[] | null) =>
    request<CreditCardAccount>(`/api/dashboard/accounts/${accountId}/settlement-patterns`, {
      method: "PATCH", body: JSON.stringify({ patterns }),
    }),

  // Stats
  monthlyStats: (year?: number, month?: number) => {
    const qs = new URLSearchParams();
    if (year) qs.set("year", String(year));
    if (month) qs.set("month", String(month));
    return request<MonthlyStats>(`/api/dashboard/stats/monthly?${qs}`);
  },
  yearlyStats: (year?: number) =>
    request<YearlyStats>(`/api/dashboard/stats/yearly${year ? `?year=${year}` : ""}`),

  // Settings
  getSettings: () => request<{ settings: Record<string, string>; groups: Record<string, { label: string; keys: string[] }>; api_key?: string }>("/api/settings"),
  updateSettings: (settings: Record<string, string>) =>
    request<{ status: string; updated: string[] }>("/api/settings", { method: "PUT", body: JSON.stringify({ settings }) }),
  regenerateApiKey: () =>
    request<{ api_key: string; message: string }>("/api/settings/api-key/regenerate", { method: "POST" }),

  // Sync
  syncGmail: () => request<{ status: string; new_transactions: number; balance: number | null; errors: string[] }>("/api/sync/gmail", { method: "POST" }),
  syncStatus: () => request<SyncStatus[]>("/api/sync/status"),

  // Brokers (read-only position sync — no order placement)
  brokers: () => request<BrokerList>("/api/brokers"),
  saxoStatus: () => request<BrokerStatus>("/api/brokers/saxo/status"),
  saxoConnect: () => request<{ authorize_url: string; environment: string }>("/api/brokers/saxo/connect", { method: "POST" }),
  saxoCompleteOAuth: (code: string, state: string) =>
    request<BrokerStatus>("/api/brokers/saxo/callback", { method: "POST", body: JSON.stringify({ code, state }) }),
  saxoDisconnect: () => request<{ status: string }>("/api/brokers/saxo/disconnect", { method: "POST" }),
  saxoHealth: () => request<{ ok: boolean }>("/api/brokers/saxo/health"),
  saxoAccounts: () => request<{ accounts: BrokerAccount[] }>("/api/brokers/saxo/accounts"),
  saxoSync: () => request<SaxoSyncResult>("/api/brokers/saxo/sync", { method: "POST" }),
  saxoSubPortfolio: () => request<SaxoSubPortfolio>("/api/brokers/saxo/sub-portfolio"),

  // Symbol classification (equity/etf/index/... — used for grouping holdings)
  listClassifications: () => request<SymbolClassification[]>("/api/dashboard/portfolio/classifications"),
  setClassification: (symbol: string, assetType: AssetType) =>
    request<SymbolClassification>(`/api/dashboard/portfolio/classifications/${encodeURIComponent(symbol)}`, {
      method: "POST", body: JSON.stringify({ asset_type: assetType }),
    }),
  backfillClassifications: () =>
    request<{ created: number; skipped: number; total_symbols: number }>("/api/dashboard/portfolio/classifications/backfill", { method: "POST" }),

  // Watchlist — tracking only, no analysis/recommendations
  watchlist: () => request<WatchlistItem[]>("/api/dashboard/watchlist"),
  addWatchlistItem: (symbol: string) =>
    request<WatchlistItem>("/api/dashboard/watchlist", { method: "POST", body: JSON.stringify({ symbol }) }),
  removeWatchlistItem: (symbol: string) =>
    request<{ status: string }>(`/api/dashboard/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" }),
};

// Re-export all types so existing imports from '@/lib/api' continue to work.
export * from "@/lib/types";
