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
  // Never silent: populated whenever a quote or FX lookup failed this
  // request (stale price shown, or a position excluded from CHF totals).
  warnings: string[];
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
  change: number;
  change_pct: number;
  unrealized_pnl: number;
  pnl_pct: number;
  market_value: number;
  weight_pct: number;
  first_bought: string | null;
  trade_count: number;
  sparkline: number[];
  // asset_type groups holdings into ETFs vs Stocks on the portfolio page.
  asset_type: AssetType;
  // Quote fetch failed this request AND the last known price is >15min old.
  price_stale: boolean;
  // No CHF exchange rate is known for this position's currency — market_value
  // and unrealized_pnl are 0.0 placeholders, not real numbers.
  fx_unavailable: boolean;
}

export interface WatchlistItem {
  id: string;
  symbol: string;
  added_at: string | null;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string | null;
  name: string | null;
  quote_unavailable: boolean;
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
export interface SettlementResult { card_account_id: string; card_account_name: string; settled_amount: number; settlement_date: string; skipped: boolean }
export interface ImportResult { imported: number; skipped: number; categorized: number; uncategorized: number; total_rows: number; log?: ImportLogEntry[]; settlements?: SettlementResult[]; format?: string; saved_profile?: string }

// Credit-card settlement patterns (Feature A settings UI)
export interface CreditCardAccount { id: string; name: string; currency: string; settlement_patterns: string[] | null }

// Generic CSV column-mapper (Feature B)
export interface ColumnMapping {
  date_col: string;
  amount_col?: string | null;
  description_col?: string | null;
  debit_col?: string | null;
  credit_col?: string | null;
  date_format: string;
  decimal_separator: string;
  invert_amount: boolean;
  currency: string;
}
export interface CsvPreview { columns: string[]; rows: Record<string, string>[]; delimiter: string; encoding: string }
export interface ImportProfile { id: string; name: string; account_id: string | null; mapping: ColumnMapping; created_at: string }

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
  warnings: string[];
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

export type AssetType = "equity" | "etf" | "index" | "crypto" | "bond" | "commodity" | "cash";
export type ClassificationSource = "auto" | "user" | "agent";

export interface SymbolClassification {
  symbol: string;
  asset_type: AssetType;
  source: ClassificationSource;
  updated_at: string;
}

