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

  if (res.status === 401 || res.status === 403) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      localStorage.removeItem("token");
      localStorage.removeItem("refreshToken");
      document.cookie = "token=; path=/; max-age=0";
      // Prevent multiple concurrent redirects
      if (!(window as any).__redirecting) {
        (window as any).__redirecting = true;
        window.location.href = "/login";
      }
    }
    throw new Error("Session expired");
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
  setAccountBalance: (accountId: string, balance: number) =>
    request<{ status: string }>(`/api/dashboard/accounts/${accountId}/set-balance`, {
      method: "POST",
      body: JSON.stringify({ balance }),
    }),
  portfolioHistory: (days = 90) => request<PortfolioSnapshot[]>(`/api/dashboard/portfolio/history?days=${days}`),
  portfolioValueTimeline: () => request<ValueTimelinePoint[]>("/api/dashboard/portfolio/value-timeline"),
  trade: (data: { symbol: string; type: string; quantity: number; price?: number; currency?: string; date?: string; fees?: number; deduct_from_cash?: boolean }) =>
    request<{ status: string }>("/api/dashboard/portfolio/trade", { method: "POST", body: JSON.stringify(data) }),
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
  publicStockAnalyses: (token: string, symbol: string) =>
    fetch(`/api/public/portfolio/${token}/analyses/${symbol}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<StockAnalysisEntry[]>; }),
  publicTrades: (token: string, symbol?: string) =>
    fetch(`/api/public/portfolio/${token}/trades${symbol ? `?symbol=${symbol}` : ""}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<Trade[]>; }),
  publicPortfolioHistory: (token: string, days = 365) =>
    fetch(`/api/public/portfolio/${token}/history?days=${days}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<PortfolioSnapshot[]>; }),
  publicValueTimeline: (token: string) =>
    fetch(`/api/public/portfolio/${token}/value-timeline`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<ValueTimelinePoint[]>; }),
  publicLivePrices: (token: string) =>
    fetch(`/api/public/portfolio/${token}/live-prices`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<Record<string, { price: number; change: number; change_pct: number }>>; }),
  publicEconomyHistory: (token: string, limit = 20) =>
    fetch(`/api/public/portfolio/${token}/economy-history?limit=${limit}`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<PortfolioAnalysis[]>; }),

  // Per-stock analyses (private)
  analysesByStock: () => request<{ current: Record<string, StockAnalysisEntry>; past: Record<string, StockAnalysisEntry> }>("/api/dashboard/portfolio/analyses/by-stock"),
  stockAnalyses: (symbol: string) => request<StockAnalysisEntry[]>(`/api/dashboard/portfolio/analyses/${symbol}`),

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
  analysisLatest: (type?: string) => request<PortfolioAnalysis>(`/api/dashboard/analysis/latest${type ? `?analysis_type=${type}` : ""}`),
  analysisList: (type?: string, limit = 20) => request<AnalysisListItem[]>(`/api/dashboard/analysis?limit=${limit}${type ? `&analysis_type=${type}` : ""}`),
  analysisDetail: (id: string) => request<PortfolioAnalysis>(`/api/dashboard/analysis/${id}`),
  economyHistory: (limit = 20) => request<PortfolioAnalysis[]>(`/api/dashboard/analysis?analysis_type=economy&limit=${limit}&full=true`),

  // Settings
  getSettings: () => request<{ settings: Record<string, string>; groups: Record<string, { label: string; keys: string[] }>; api_key?: string }>("/api/settings"),
  updateSettings: (settings: Record<string, string>) =>
    request<{ status: string; updated: string[] }>("/api/settings", { method: "PUT", body: JSON.stringify({ settings }) }),
  regenerateApiKey: () =>
    request<{ api_key: string; message: string }>("/api/settings/api-key/regenerate", { method: "POST" }),

  // Sync
  syncGmail: () => request<{ status: string; new_transactions: number; balance: number | null; errors: string[] }>("/api/sync/gmail", { method: "POST" }),
  syncStatus: () => request<SyncStatus[]>("/api/sync/status"),

  // Brokers
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
  saxoPrecheck: (order: SaxoOrderInput) =>
    request<SaxoPrecheckResult>("/api/brokers/saxo/orders/precheck", { method: "POST", body: JSON.stringify(order) }),
  saxoPlaceOrder: (order: SaxoOrderInput) =>
    request<{ order_id: string }>("/api/brokers/saxo/orders", { method: "POST", body: JSON.stringify(order) }),
  saxoCancelOrder: (orderId: string, accountKey: string) =>
    request<{ status: string }>(`/api/brokers/saxo/orders/${orderId}?account_key=${encodeURIComponent(accountKey)}`, { method: "DELETE" }),
  saxoModifyOrder: (input: SaxoModifyInput) =>
    request<{ status: string }>("/api/brokers/saxo/orders", { method: "PATCH", body: JSON.stringify(input) }),
  saxoListOrders: (accountKey: string) =>
    request<{ orders: SaxoOrderSummary[] }>(`/api/brokers/saxo/orders?account_key=${encodeURIComponent(accountKey)}`),

  // Benchmark comparison (individual stocks TWR vs S&P 500)
  benchmarkComparison: (params: { range: string; benchmark?: string; start?: string; end?: string }) => {
    const qs = new URLSearchParams();
    qs.set("range", params.range);
    if (params.benchmark) qs.set("benchmark", params.benchmark);
    if (params.start) qs.set("start", params.start);
    if (params.end) qs.set("end", params.end);
    return request<BenchmarkComparison>(`/api/dashboard/portfolio/benchmark-comparison?${qs}`);
  },
  listClassifications: () => request<SymbolClassification[]>("/api/dashboard/portfolio/classifications"),
  setClassification: (symbol: string, assetType: string) =>
    request<SymbolClassification>(`/api/dashboard/portfolio/classifications/${encodeURIComponent(symbol)}`, {
      method: "POST", body: JSON.stringify({ asset_type: assetType }),
    }),
  backfillClassifications: () =>
    request<{ created: number; skipped: number; total_symbols: number }>("/api/dashboard/portfolio/classifications/backfill", { method: "POST" }),

  // Post-Mortems
  postMortems: (params?: { symbol?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.symbol) qs.set("symbol", params.symbol);
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<PostMortem[]>(`/api/dashboard/post-mortems?${qs}`);
  },
  createPostMortem: (body: PostMortemInput) =>
    request<PostMortem>("/api/dashboard/post-mortems", { method: "POST", body: JSON.stringify(body) }),
  updatePostMortem: (id: string, body: Partial<PostMortemInput>) =>
    request<PostMortem>(`/api/dashboard/post-mortems/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deletePostMortem: (id: string) =>
    request<void>(`/api/dashboard/post-mortems/${id}`, { method: "DELETE" }),

  // Buy Assessments
  buyAssessments: (params?: { symbol?: string; recommendation?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.symbol) qs.set("symbol", params.symbol);
    if (params?.recommendation) qs.set("recommendation", params.recommendation);
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<BuyAssessment[]>(`/api/dashboard/buy-assessments?${qs}`);
  },
  createBuyAssessment: (body: BuyAssessmentInput) =>
    request<BuyAssessment>("/api/dashboard/buy-assessments", { method: "POST", body: JSON.stringify(body) }),
  updateBuyAssessment: (id: string, body: Partial<BuyAssessmentInput>) =>
    request<BuyAssessment>(`/api/dashboard/buy-assessments/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteBuyAssessment: (id: string) =>
    request<void>(`/api/dashboard/buy-assessments/${id}`, { method: "DELETE" }),

  // Public journal
  publicJournal: (token: string) =>
    fetch(`/api/public/portfolio/${token}/journal`).then(r => { if (!r.ok) throw new Error("Not found"); return r.json() as Promise<{ post_mortems: PostMortem[]; buy_assessments: BuyAssessment[] }>; }),

  // Tools / Signal Evaluation
  toolsLeaderboard: () => request<ToolLeaderboardEntry[]>("/api/dashboard/tools/leaderboard"),
  toolsDrillDown: (name: string, windowDays = 60) =>
    request<ToolDrillDown>(`/api/dashboard/tools/drill-down/${encodeURIComponent(name)}?window_days=${windowDays}`),
  toolsRegimeBreakdown: (name: string) =>
    request<ToolRegimeBreakdown>(`/api/dashboard/tools/regime-breakdown/${encodeURIComponent(name)}`),
  toolsCorrelationMatrix: () => request<ToolCorrelationMatrix>("/api/dashboard/tools/correlation-matrix"),
  toolsPendingProposals: () => request<ToolWeightProposal[]>("/api/dashboard/tools/pending-proposals"),
  resolveProposal: (id: string, resolution: "approved" | "rejected", resolvedBy?: string) =>
    request<{ status: string }>(`/api/dashboard/tools/proposals/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ resolution, resolved_by: resolvedBy ?? process.env.NEXT_PUBLIC_ADMIN_NAME ?? "admin" }),
    }),

  // AI Trading (pending orders)
  listPendingOrders: (status?: PendingOrderStatus) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<{ pending_orders: PendingOrder[] }>(`/api/dashboard/trading/pending-orders${qs}`);
  },
  approvePendingOrder: (id: string) =>
    request<PendingOrder>(`/api/dashboard/trading/pending-orders/${encodeURIComponent(id)}/approve`, { method: "POST" }),
  rejectPendingOrder: (id: string, reason?: string) =>
    request<PendingOrder>(`/api/dashboard/trading/pending-orders/${encodeURIComponent(id)}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  expirePendingOrder: (id: string) =>
    request<PendingOrder>(`/api/dashboard/trading/pending-orders/${encodeURIComponent(id)}/expire`, { method: "POST" }),
  expireStalePendingOrders: () =>
    request<{ expired: number }>("/api/dashboard/trading/expire-stale", { method: "POST" }),
};

// Types
export interface Overview {
  display_name: string;
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
  net_deposits: number;
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

export interface Trade { id: string; symbol: string; type: string; quantity: number; price: number; fees: number; currency: string; date: string; total: number; total_chf: number; fees_chf: number }
export interface ValueTimelinePoint { date: string; value: number; cost: number; pnl: number; trades: { symbol: string; type: string; quantity: number; price: number }[] | null }
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
  analysis_type: string;
  content: {
    market_summary: string;
    market_sentiment: string;
    stocks?: StockAnalysis[];
    key_indicators?: { name: string; value: string; trend: string }[];
    outlook?: string;
    risks?: string[];
    opportunities?: string[];
    analyzed_at: string;
  };
  created_at: string;
}

export interface AnalysisListItem {
  id: string;
  analysis_type: string;
  market_sentiment: string | null;
  stocks_count: number;
  created_at: string;
}

export interface StockAnalysisEntry {
  analysis_id: string;
  stock: StockAnalysis;
  market_summary: string;
  market_sentiment: string;
  created_at: string;
}

export interface PublicPortfolio {
  display_name: string;
  total_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  cash_balance: number;
  base_currency: string;
  positions_count: number;
  positions: Position[];
  stock_analyses: Record<string, StockAnalysisEntry>;
  past_stock_analyses?: Record<string, StockAnalysisEntry>;
  economy_analysis: PortfolioAnalysis | null;
  trades?: Trade[];
}

export interface SyncResult { status: string; records_synced: number; message: string }
export interface SyncStatus { source: string; status: string; records_synced: number; synced_at: string | null; error_message: string | null }

export interface BrokerDescriptor {
  name: string;
  label: string;
  environments: string[];
  trading_available: boolean;
}
export interface BrokerEnvironmentOption { value: string; label: string; enabled: boolean }
export interface BrokerList { brokers: BrokerDescriptor[]; saxo_environments: BrokerEnvironmentOption[] }
export interface BrokerStatus {
  state: "disabled" | "setup_required" | "needs_auth" | "connecting" | "connected" | "error";
  environment: string | null;
  detail?: string | null;
  last_error?: string | null;
}
export interface BrokerAccount {
  external_id: string;
  display_name: string;
  currency: string;
  environment: string;
}

export interface SaxoSyncResult {
  status: "ok" | "noop";
  reason?: string;
  account_id?: string;
  cash_balance?: number | null;
  cash_currency?: string;
  positions_upserted?: number;
  positions_removed?: number;
}

export interface SaxoSubAccount {
  account_id: string;
  name: string;
  currency: string;
  cash: number;
  cash_updated_at: string | null;
  positions: {
    id: string;
    symbol: string;
    name: string;
    quantity: number;
    avg_cost_price: number;
    currency: string;
    last_price: number | null;
    unrealized_pnl: number | null;
    market_value: number;
  }[];
}

export interface SaxoSubPortfolio {
  connected: boolean;
  accounts: SaxoSubAccount[];
}

export interface SaxoOrderInput {
  account_key: string;
  symbol: string;
  buy_sell: "Buy" | "Sell";
  amount: number;
  order_type: "Market" | "Limit" | "Stop" | "StopLimit";
  duration?: "DayOrder" | "GoodTillCancel";
  limit_price?: number;
  stop_price?: number;
  asset_type?: string;
}

export interface SaxoModifyInput {
  order_id: string;
  account_key: string;
  amount?: number;
  limit_price?: number;
  stop_price?: number;
  duration?: "DayOrder" | "GoodTillCancel";
}

export interface SaxoPrecheckResult {
  ok: boolean;
  estimated_cash_required: number | null;
  estimated_fees: number | null;
  currency: string | null;
  warnings: string[];
  error_message: string | null;
}

export interface SaxoOrderSummary {
  order_id: string;
  symbol: string;
  uic: number;
  asset_type: string;
  buy_sell: string;
  amount: number;
  order_type: string;
  status: string;
  price: number | null;
}

export type AssetType = "equity" | "etf" | "index" | "crypto" | "bond" | "commodity" | "cash";
export type ClassificationSource = "auto" | "user" | "agent";

export interface SymbolClassification {
  symbol: string;
  asset_type: AssetType;
  source: ClassificationSource;
  updated_at: string;
}

export interface BenchmarkPortfolioPoint {
  date: string;
  index: number;
  value_chf: number;
  contributors?: Record<string, number>;  // symbol -> contribution_pp
}
export interface BenchmarkSeriesPoint { date: string; index: number; close: number }
export interface BenchmarkCountedSymbol {
  symbol: string;
  asset_type: AssetType;
  source: ClassificationSource;
  active_from: string;       // ISO date — first day held in window
  active_to: string | null;  // ISO date — last day held, or null if still held
  current_qty: number;
  contribution_pp: number;
  // Legacy fields for backward-compat
  quantity?: number;
  first_tx_date?: string;
}
export interface BenchmarkExcludedSymbol {
  symbol: string;
  asset_type: AssetType;
  source: ClassificationSource;
  reason: "classified_non_equity" | "no_transactions" | "saxo_only" | "closed_before_window" | "closed";
}
export interface BenchmarkComparison {
  range: string;
  start_date: string;
  end_date: string;
  benchmark_symbol: string;
  portfolio_series: BenchmarkPortfolioPoint[];
  benchmark_series: BenchmarkSeriesPoint[];
  summary: {
    portfolio_return_pct: number;
    benchmark_return_pct: number;
    alpha_pct: number;
    avg_daily_alpha_pp: number;
    days_portfolio_ahead: number;
    total_days_compared: number;
  };
  counted_symbols: BenchmarkCountedSymbol[];
  excluded_symbols: BenchmarkExcludedSymbol[];
  caveats: string[];
}

export interface PostMortem {
  id: string;
  user_id: string;
  symbol: string;
  analysis_id: string | null;
  entry_price: number;
  exit_price: number;
  pnl_pct: number;
  notes: string | null;
  created_at: string;
}

export interface PostMortemInput {
  symbol: string;
  entry_price: number;
  exit_price: number;
  notes?: string;
  analysis_id?: string;
}

export interface BuyAssessment {
  id: string;
  user_id: string;
  symbol: string;
  recommendation: "buy" | "hold" | "watch" | "avoid";
  target_price: number | null;
  stop_loss: number | null;
  thesis: string;
  risk_factors: string | null;
  conviction: number;
  time_horizon: "short" | "medium" | "long" | null;
  assessed_at: string;
  created_at: string;
  updated_at: string;
}

export interface BuyAssessmentInput {
  symbol: string;
  recommendation: "buy" | "hold" | "watch" | "avoid";
  target_price?: number;
  stop_loss?: number;
  thesis: string;
  risk_factors?: string;
  conviction: number;
  time_horizon?: "short" | "medium" | "long";
  assessed_at?: string;
}

export interface ToolLeaderboardEntry {
  tool_name: string;
  ic_30d: number | null;
  ic_60d: number | null;
  weight: number;
  locked: boolean;
  last_weight_change: string | null;
  observation_count: number;
}

export interface ToolSignalEntry {
  id: string;
  run_id: string;
  symbol: string | null;
  signal_score: number | null;
  regime: string | null;
  run_timestamp: string;
  forward_return_1d: number | null;
  forward_return_5d: number | null;
  forward_return_20d: number | null;
  alpha_5d: number | null;
}

export interface ToolICPoint {
  date: string;
  ic: number;
  n: number;
}

export interface ToolDrillDown {
  tool_name: string;
  recent_signals: ToolSignalEntry[];
  ic_time_series: ToolICPoint[];
}

export interface RegimeStat {
  ic: number | null;
  n: number;
}

export interface ToolRegimeBreakdown {
  expansionary: RegimeStat;
  inflationary: RegimeStat;
  recessionary: RegimeStat;
  stagflationary: RegimeStat;
  [key: string]: RegimeStat;
}

export interface ToolCorrelationMatrix {
  tools: string[];
  matrix: number[][];
}

export interface ToolWeightProposal {
  id: string;
  tool_name: string;
  current_weight: number;
  proposed_weight: number;
  rationale: string;
  ic_30d?: number | null;
  ic_60d?: number | null;
  observation_count?: number;
  created_at?: string;
}

// ── AI Trading ───────────────────────────────────────────────────────────────

export type PendingOrderAction = "place" | "modify" | "cancel";
export type PendingOrderMode = "semi" | "auto";
export type PendingOrderStatus =
  | "pending_approval"
  | "approved"
  | "placed"
  | "rejected"
  | "failed"
  | "expired";

export interface PendingOrder {
  pending_order_id: string;
  user_id: string;
  account_key: string;
  symbol: string | null;
  action: PendingOrderAction;
  target_order_id: string | null;
  buy_sell: "Buy" | "Sell" | null;
  amount: number | null;
  order_type: string | null;
  duration: string | null;
  limit_price: number | null;
  stop_price: number | null;
  mode: PendingOrderMode;
  status: PendingOrderStatus;
  buy_assessment_id: string | null;
  rationale: string | null;
  estimated_cash_required_chf: number | null;
  estimated_fees_chf: number | null;
  currency: string | null;
  idempotency_key: string;
  expires_at: string | null;
  created_at: string | null;
  approved_at: string | null;
  placed_at: string | null;
  rejected_at: string | null;
  rejected_reason: string | null;
  broker_order_id: string | null;
  broker_response: Record<string, unknown> | null;
}

export interface TradingSettings {
  trading_ai_enabled: string;
  trading_mode: string;
  trading_allowed_actions: string;
  trading_symbol_whitelist: string;
  trading_symbol_blacklist: string;
  trading_order_max_chf: string;
  trading_daily_count_max: string;
  trading_daily_chf_max: string;
  trading_position_size_max_pct: string;
  trading_per_symbol_max_pct: string;
  trading_semi_approval_timeout_s: string;
  trading_timezone: string;
}
