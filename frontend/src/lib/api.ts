// All API calls go through the Next.js proxy at /api/* (same origin)
// The proxy forwards to the backend at localhost:8001

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      localStorage.removeItem("token");
      localStorage.removeItem("refreshToken");
      window.location.href = "/login";
    }
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Invalid credentials");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
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
  portfolioHistory: (days = 90) => request<PortfolioSnapshot[]>(`/api/dashboard/portfolio/history?days=${days}`),
  trade: (data: { symbol: string; type: string; quantity: number; price?: number; currency?: string; date?: string; fees?: number; deduct_from_cash?: boolean }) =>
    request<{ status: string }>("/api/dashboard/portfolio/trade", { method: "POST", body: JSON.stringify(data) }),
  trades: (symbol?: string) =>
    request<{ id: string; symbol: string; type: string; quantity: number; price: number; fees: number; currency: string; date: string; total: number }[]>(`/api/dashboard/portfolio/trades${symbol ? `?symbol=${symbol}` : ""}`),
  updatePosition: (id: string, data: { quantity?: number; avg_cost_price?: number }) =>
    request<{ status: string }>(`/api/dashboard/portfolio/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePosition: (id: string) =>
    request<{ status: string }>(`/api/dashboard/portfolio/${id}`, { method: "DELETE" }),
  priceChart: (ticker: string, range = "1y") =>
    request<{ ticker: string; range: string; data: { date: string; close: number }[] }>(`/api/dashboard/portfolio/chart/${ticker}?range=${range}`),
  stockTransactions: (symbol?: string) =>
    request<StockTransaction[]>(`/api/dashboard/portfolio/transactions${symbol ? `?symbol=${symbol}` : ""}`),

  // Transactions
  transactions: (params?: { category_id?: string; from_date?: string; to_date?: string; search?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)));
    return request<TransactionItem[]>(`/api/dashboard/transactions?${qs}`);
  },
  createTransaction: (data: CreateTransaction) =>
    request<TransactionItem>("/api/dashboard/transactions", { method: "POST", body: JSON.stringify(data) }),
  updateTransaction: (id: string, data: Partial<TransactionItem>) =>
    request<TransactionItem>(`/api/dashboard/transactions/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

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

  // Recurring
  recurring: () => request<RecurringExpense[]>("/api/dashboard/recurring"),
  createRecurring: (data: CreateRecurring) =>
    request<RecurringExpense>("/api/dashboard/recurring", { method: "POST", body: JSON.stringify(data) }),

  // Cash Flow
  cashflow: (months = 6) => request<CashFlowMonth[]>(`/api/dashboard/cashflow?months=${months}`),

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

  // Stats
  monthlyStats: (year?: number, month?: number) => {
    const qs = new URLSearchParams();
    if (year) qs.set("year", String(year));
    if (month) qs.set("month", String(month));
    return request<MonthlyStats>(`/api/dashboard/stats/monthly?${qs}`);
  },
  yearlyStats: (year?: number) =>
    request<YearlyStats>(`/api/dashboard/stats/yearly${year ? `?year=${year}` : ""}`),

  // Analysis
  analysisLatest: () => request<PortfolioAnalysis>("/api/dashboard/analysis/latest"),
  analysisList: (limit = 10) => request<AnalysisListItem[]>(`/api/dashboard/analysis?limit=${limit}`),
  analysisDetail: (id: string) => request<PortfolioAnalysis>(`/api/dashboard/analysis/${id}`),

  // Settings
  getSettings: () => request<{ settings: Record<string, string>; groups: Record<string, { label: string; keys: string[] }> }>("/api/settings"),
  updateSettings: (settings: Record<string, string>) =>
    request<{ status: string; updated: string[] }>("/api/settings", { method: "PUT", body: JSON.stringify({ settings }) }),

  // Sync
  syncGmail: () => request<{ status: string; new_transactions: number; balance: number | null; errors: string[] }>("/api/sync/gmail", { method: "POST" }),
  syncStatus: () => request<SyncStatus[]>("/api/sync/status"),
};

// Types
export interface Overview {
  net_worth: number;
  portfolio_value: number;
  portfolio_pnl: number;
  portfolio_pnl_pct: number;
  accounts: { id: string; name: string; type: string; currency: string; balance: number }[];
  recent_transactions: { id: string; date: string; merchant: string; amount: number; currency: string; category_name: string | null }[];
  budget_health: { id: string; name: string; amount: number; period: string; spent: number }[];
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  cash_balance: number;
  positions_count: number;
  positions: Position[];
}

export interface Position {
  id: string;
  symbol: string;
  name: string;
  quantity: number;
  avg_cost_price: number;
  currency: string;
  last_price: number | null;
  change: number;
  change_pct: number;
  unrealized_pnl: number;
  pnl_pct: number;
  market_value: number;
  weight_pct: number;
  first_bought: string | null;
  trade_count: number;
  sparkline: number[];
}

export interface PortfolioSnapshot { date: string; value: number; pnl: number }
export interface StockTransaction { id: string; symbol: string; type: string; quantity: number; price: number; fees: number; currency: string; executed_at: string }

export interface TransactionItem {
  id: string; account_id: string; date: string; merchant: string; amount: number; currency: string;
  original_amount: number | null; original_currency: string | null; category_id: string | null;
  category_name: string | null; parent_category_name: string | null; notes: string | null;
  viseca_transaction_id: string | null; created_at: string;
}
export interface CreateTransaction { account_id: string; date: string; merchant: string; amount: number; currency?: string; category_id?: string; notes?: string }

export interface Category { id: string; name: string; type: string; icon: string | null; color: string | null; parent_id: string | null }

export interface Budget { id: string; name: string; category_id: string | null; category_name: string | null; amount: number; period: string; start_date: string; end_date: string | null; spent: number; remaining: number; pct_used: number }
export interface CreateBudget { name: string; category_id?: string; amount: number; period?: string; start_date: string; end_date?: string }

export interface SavingsGoal { id: string; name: string; target_amount: number; current_amount: number; target_date: string | null; currency: string; progress_pct: number; created_at: string }
export interface CreateGoal { name: string; target_amount: number; current_amount?: number; target_date?: string; currency?: string }

export interface Milestone { id: string; name: string; description: string | null; target_date: string | null; target_net_worth: number | null; target_savings: number | null; achieved: boolean; achieved_at: string | null }
export interface CreateMilestone { name: string; description?: string; target_date?: string; target_net_worth?: number; target_savings?: number }

export interface RecurringExpense { id: string; name: string; amount: number; currency: string; frequency: string; next_due_date: string; category_id: string | null; category_name: string | null; active: boolean }
export interface CreateRecurring { name: string; amount: number; currency?: string; frequency?: string; next_due_date: string; category_id?: string }

export interface CashFlowMonth { month: string; income: number; expenses: number; net: number }
export interface MerchantRule { id: string; name: string; patterns: string; default_category_id: string | null; category_name: string | null; is_system: boolean }

export interface ImportLogEntry { msg: string; detail: string }
export interface ImportResult { imported: number; skipped: number; categorized: number; uncategorized: number; total_rows: number; log?: ImportLogEntry[] }

export interface MonthlyStats {
  period: { year: number; month: number; start: string; end: string };
  summary: { income: number; expenses: number; net: number; savings_rate: number; avg_daily_spend: number; txn_count: number };
  comparison: Record<string, { current: number; previous: number; change: number; change_pct: number }>;
  categories: { id: string | null; name: string; color: string | null; total: number; count: number }[];
  top_merchants: { merchant: string; total: number; count: number }[];
  daily_spend: { date: string; amount: number }[];
  spending_velocity: { date: string; cumulative: number }[];
  budget_vs_actual: { name: string; category: string; budget: number; spent: number; remaining: number; pct: number }[];
  recurring_vs_discretionary: { recurring: number; discretionary: number };
  account_breakdown: { name: string; type: string; total: number; count: number }[];
}

export interface YearlyStats {
  period: { year: number };
  summary: { income: number; expenses: number; net: number; savings_rate: number; avg_monthly_spend: number; avg_monthly_income: number; txn_count: number };
  comparison: Record<string, { current: number; previous: number; change: number; change_pct: number }>;
  monthly: { month: number; income: number; expenses: number; net: number }[];
  categories: { id: string | null; name: string; color: string | null; total: number; count: number }[];
  category_trends: { month: number; category: string; total: number }[];
  top_merchants: { merchant: string; total: number; count: number }[];
  net_worth_history: { date: string; value: number; pnl: number }[];
}

export interface StockAnalysis {
  symbol: string;
  action: string;
  current_price: number;
  entry_price: number;
  unrealized_pnl_pct: number;
  rationale: string;
  key_risks: string[];
  key_catalysts: string[];
}

export interface PortfolioAnalysis {
  id: string;
  content: {
    market_summary: string;
    market_sentiment: string;
    stocks: StockAnalysis[];
    analyzed_at: string;
  };
  created_at: string;
}

export interface AnalysisListItem {
  id: string;
  market_sentiment: string | null;
  stocks_count: number;
  created_at: string;
}

export interface SyncResult { status: string; records_synced: number; message: string }
export interface SyncStatus { source: string; status: string; records_synced: number; synced_at: string | null; error_message: string | null }
