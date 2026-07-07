import type { ComponentType } from "react";
import { NetWorthWidget } from "./net-worth-widget";
import { AccountsWidget } from "./accounts-widget";
import { PortfolioSnapshotWidget } from "./portfolio-snapshot-widget";
import { RecentTransactionsWidget } from "./recent-transactions-widget";
import { BudgetHealthWidget } from "./budget-health-widget";
import { UpcomingPaymentsWidget } from "./upcoming-payments-widget";

export type WidgetId =
  | "net-worth"
  | "accounts"
  | "portfolio-snapshot"
  | "recent-transactions"
  | "budget-health"
  | "upcoming-payments";

export interface WidgetDef {
  id: WidgetId;
  label: string;
  component: ComponentType;
  /** grid column span in the 2-column dashboard grid */
  span: "full" | "half";
}

/** Every widget the dashboard can show, in default order. Adding a new
 * widget is just adding an entry here + a component in this directory. */
export const WIDGET_REGISTRY: WidgetDef[] = [
  { id: "net-worth", label: "Net worth summary", component: NetWorthWidget, span: "half" },
  { id: "portfolio-snapshot", label: "Portfolio snapshot", component: PortfolioSnapshotWidget, span: "half" },
  { id: "accounts", label: "Accounts", component: AccountsWidget, span: "half" },
  { id: "upcoming-payments", label: "Upcoming payments", component: UpcomingPaymentsWidget, span: "half" },
  { id: "recent-transactions", label: "Recent transactions", component: RecentTransactionsWidget, span: "half" },
  { id: "budget-health", label: "Budget health", component: BudgetHealthWidget, span: "half" },
];

export const WIDGET_BY_ID: Record<WidgetId, WidgetDef> = Object.fromEntries(
  WIDGET_REGISTRY.map((w) => [w.id, w]),
) as Record<WidgetId, WidgetDef>;

export interface LayoutItem {
  id: WidgetId;
  visible: boolean;
}

/** Default layout = current arrangement, everything visible. */
export const DEFAULT_LAYOUT: LayoutItem[] = WIDGET_REGISTRY.map((w) => ({ id: w.id, visible: true }));
