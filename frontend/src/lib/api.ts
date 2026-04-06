const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
      localStorage.removeItem("refreshToken");
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
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
  createCategory: (data: { name: string; type: string }) =>
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

  // Analysis
  analysisLatest: (type?: string) =>
    request<AnalysisResult[]>(`/api/dashboard/analysis/latest${type ? `?analysis_type=${type}` : ""}`),
  runAnalysis: (type: string) =>
    request<AnalysisResult>("/api/dashboard/analysis/run", { method: "POST", body: JSON.stringify({ analysis_type: type }) }),

  // Sync
  syncSaxo: () => request<SyncResult>("/api/sync/saxo", { method: "POST" }),
  syncViseca: () => request<SyncResult>("/api/sync/viseca", { method: "POST" }),
  syncStatus: () => request<SyncStatus[]>("/api/sync/status"),
};

// Types
export interface Overview {
  net_worth: number;
  portfolio_value: number;
  portfolio_pnl: number;
  portfolio_pnl_pct: number;
  accounts: { id: string; name: string; type: string; currency: string }[];
  recent_transactions: { id: string; date: string; merchant: string; amount: number; currency: string; category_name: string | null }[];
  budget_health: { id: string; name: string; amount: number; period: string; spent: number }[];
}

export interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
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
  last_price_at: string | null;
  unrealized_pnl: number | null;
  market_value: number | null;
  weight_pct: number | null;
}

export interface PortfolioSnapshot { snapshot_date: string; total_value: number; total_cost: number; total_pnl: number }
export interface StockTransaction { id: string; symbol: string; type: string; quantity: number; price: number; fees: number; currency: string; executed_at: string }

export interface TransactionItem {
  id: string; account_id: string; date: string; merchant: string; amount: number; currency: string;
  original_amount: number | null; original_currency: string | null; category_id: string | null;
  category_name: string | null; notes: string | null; viseca_transaction_id: string | null; created_at: string;
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
export interface AnalysisResult {
  id: string;
  analysis_type: string;
  content: {
    summary?: string;
    risk_level?: string;
    key_insights?: string[];
    recommendations?: string[];
    sector_breakdown?: Record<string, string>;
    position_notes?: Record<string, string>;
    macro_outlook?: string;
  };
  model_used: string | null;
  created_at: string;
}

export interface SyncResult { status: string; records_synced: number; message: string }
export interface SyncStatus { source: string; status: string; records_synced: number; synced_at: string | null; error_message: string | null }
