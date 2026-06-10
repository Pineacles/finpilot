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

// Re-export all types so existing imports from '@/lib/api' continue to work.
export * from "@/lib/types";
