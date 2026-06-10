// Type definitions for the FinPilot API client.
// These are re-exported from api.ts for backward compatibility.
// For new code, import directly from '@/lib/types'.

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
