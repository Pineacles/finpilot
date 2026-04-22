"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GlassCard } from "@/components/glass-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Bot, CheckCircle2, XCircle, Clock, AlertTriangle } from "lucide-react";
import { api, type PendingOrder, type PendingOrderStatus } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTimeUntil(iso: string | null): string {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "Expired";
  const mins = Math.floor(diff / 60000);
  const secs = Math.floor((diff % 60000) / 1000);
  if (mins >= 60) return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function formatSince(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function truncate(s: string | null, max: number): string {
  if (!s) return "";
  return s.length > max ? s.slice(0, max) + "…" : s;
}

const MODE_BADGE: Record<string, string> = {
  semi: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  auto: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400",
};

const ACTION_BADGE: Record<string, string> = {
  place: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  modify: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400",
  cancel: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400",
};

const STATUS_BADGE: Record<string, string> = {
  pending_approval: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  approved: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400",
  placed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
  expired: "bg-muted text-muted-foreground",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ExpiryCountdown({ expiresAt }: { expiresAt: string | null }) {
  const [label, setLabel] = useState(() => formatTimeUntil(expiresAt));
  useEffect(() => {
    const id = setInterval(() => setLabel(formatTimeUntil(expiresAt)), 1000);
    return () => clearInterval(id);
  }, [expiresAt]);
  if (!expiresAt) return null;
  const expired = new Date(expiresAt).getTime() <= Date.now();
  return (
    <span className={`text-[11px] font-mono ${expired ? "text-red-500" : "text-muted-foreground"}`}>
      {expired ? "Expired" : `expires in ${label}`}
    </span>
  );
}

function OrderCard({
  order,
  onApprove,
  onReject,
}: {
  order: PendingOrder;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isPending = order.status === "pending_approval";

  return (
    <div className="border border-border rounded-2xl p-4 space-y-2.5 bg-card/40">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-[15px]">{order.symbol || "—"}</span>
          <Badge className={`rounded-lg text-[11px] ${ACTION_BADGE[order.action] || ""}`}>
            {order.action}
          </Badge>
          {order.buy_sell && (
            <Badge className={`rounded-lg text-[11px] ${order.buy_sell === "Buy" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" : "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400"}`}>
              {order.buy_sell}
            </Badge>
          )}
          <Badge className={`rounded-lg text-[11px] ${MODE_BADGE[order.mode] || ""}`}>
            {order.mode}
          </Badge>
          <Badge className={`rounded-lg text-[11px] ${STATUS_BADGE[order.status] || ""}`}>
            {order.status.replace("_", " ")}
          </Badge>
        </div>
        <span className="text-[11px] text-muted-foreground shrink-0">{formatSince(order.created_at)}</span>
      </div>

      {/* Order details */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
        {order.amount != null && <span>{order.amount} @ {order.order_type}</span>}
        {order.limit_price != null && <span>Limit {order.limit_price.toFixed(2)}</span>}
        {order.estimated_cash_required_chf != null && (
          <span>~{order.estimated_cash_required_chf.toFixed(2)} CHF</span>
        )}
        {order.estimated_fees_chf != null && order.estimated_fees_chf > 0 && (
          <span>fees ~{order.estimated_fees_chf.toFixed(2)} CHF</span>
        )}
      </div>

      {/* Rationale */}
      {order.rationale && (
        <div className="text-[12px] text-foreground/70">
          {expanded ? order.rationale : truncate(order.rationale, 140)}
          {order.rationale.length > 140 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="ml-1.5 text-primary text-[11px] underline"
            >
              {expanded ? "less" : "more"}
            </button>
          )}
        </div>
      )}

      {/* Expiry countdown (semi only) */}
      {isPending && order.mode === "semi" && (
        <ExpiryCountdown expiresAt={order.expires_at} />
      )}

      {/* Error/rejection reason */}
      {order.rejected_reason && (
        <p className="text-[11px] text-red-500">{order.rejected_reason}</p>
      )}

      {/* Broker order ID */}
      {order.broker_order_id && (
        <p className="text-[11px] text-muted-foreground font-mono">Broker ID: {order.broker_order_id}</p>
      )}

      {/* Actions */}
      {isPending && (
        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            className="rounded-xl flex-1"
            onClick={() => onApprove(order.pending_order_id)}
          >
            <CheckCircle2 className="h-4 w-4 mr-1.5" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="rounded-xl flex-1"
            onClick={() => onReject(order.pending_order_id)}
          >
            <XCircle className="h-4 w-4 mr-1.5" />
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PendingOrdersCard() {
  const [orders, setOrders] = useState<PendingOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<PendingOrderStatus | "">("");

  // Approve dialog
  const [approveId, setApproveId] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [approveResult, setApproveResult] = useState<PendingOrder | null>(null);

  // Reject dialog
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [rejectError, setRejectError] = useState<string | null>(null);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.listPendingOrders(statusFilter || undefined);
      setOrders(res.pending_orders);
    } catch {
      // Silently ignore — card renders nothing on error
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  // On mount: expire stale then load
  useEffect(() => {
    api.expireStalePendingOrders().catch(() => {}).then(() => load());
    // Poll every 30 seconds
    pollingRef.current = setInterval(load, 30_000);
    // Refetch on tab focus
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const handleApprove = async (id: string) => {
    setApproveId(id);
    setApproveError(null);
    setApproveResult(null);
  };

  const handleApproveConfirm = async () => {
    if (!approveId) return;
    setApproving(true);
    setApproveError(null);
    try {
      const result = await api.approvePendingOrder(approveId);
      setApproveResult(result as unknown as PendingOrder);
      await load();
    } catch (e: any) {
      setApproveError(e?.message || "Approve failed");
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async (id: string) => {
    setRejectId(id);
    setRejectReason("");
    setRejectError(null);
  };

  const handleRejectConfirm = async () => {
    if (!rejectId) return;
    setRejecting(true);
    setRejectError(null);
    try {
      await api.rejectPendingOrder(rejectId, rejectReason || undefined);
      setRejectId(null);
      await load();
    } catch (e: any) {
      setRejectError(e?.message || "Reject failed");
    } finally {
      setRejecting(false);
    }
  };

  if (!loading && orders.length === 0 && !statusFilter) return null;

  const pendingCount = orders.filter(o => o.status === "pending_approval").length;

  const STATUS_FILTER_OPTIONS: { value: PendingOrderStatus | ""; label: string }[] = [
    { value: "", label: "All" },
    { value: "pending_approval", label: "Pending" },
    { value: "placed", label: "Placed" },
    { value: "rejected", label: "Rejected" },
    { value: "failed", label: "Failed" },
    { value: "expired", label: "Expired" },
  ];

  return (
    <>
      <GlassCard delay={0.52}>
        <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
              <Bot className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold flex items-center gap-2">
                AI Orders
                {pendingCount > 0 && (
                  <span className="text-[12px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    {pendingCount} need approval
                  </span>
                )}
              </h2>
              <p className="text-[12px] text-muted-foreground">Orders submitted by the AI agent</p>
            </div>
          </div>
          <div className="flex gap-1.5">
            {STATUS_FILTER_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setStatusFilter(opt.value)}
                className={`text-[11px] px-2.5 py-1 rounded-lg transition-colors cursor-pointer ${
                  statusFilter === opt.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-accent text-muted-foreground hover:bg-muted"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="text-center py-8 text-muted-foreground text-[13px]">
            <Clock className="h-5 w-5 mx-auto mb-2 animate-spin" />
            Loading…
          </div>
        ) : orders.length === 0 ? (
          <p className="text-[13px] text-muted-foreground text-center py-6">No orders for this filter.</p>
        ) : (
          <div className="space-y-3">
            {orders.map(order => (
              <OrderCard
                key={order.pending_order_id}
                order={order}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            ))}
          </div>
        )}
      </GlassCard>

      {/* Approve Dialog */}
      <Dialog open={!!approveId} onOpenChange={open => { if (!open) { setApproveId(null); setApproveResult(null); setApproveError(null); } }}>
        <DialogContent className="rounded-3xl max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-500" />
              Confirm Approval
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {approveResult ? (
              <div className="rounded-xl p-3 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-[13px]">
                <p className="font-semibold">Order placed successfully</p>
                {approveResult.broker_order_id && (
                  <p className="mt-1 font-mono text-[11px]">Broker ID: {approveResult.broker_order_id}</p>
                )}
              </div>
            ) : (
              <>
                <p className="text-[13px] text-muted-foreground">
                  This will immediately submit the order to Saxo. Prices may have moved since the order was created.
                </p>
                {approveError && (
                  <p className="text-[13px] text-red-600 dark:text-red-400">{approveError}</p>
                )}
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1 rounded-xl" onClick={() => setApproveId(null)} disabled={approving}>
                    Cancel
                  </Button>
                  <Button className="flex-1 rounded-xl" onClick={handleApproveConfirm} disabled={approving}>
                    {approving ? "Approving…" : "Approve & Place"}
                  </Button>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={!!rejectId} onOpenChange={open => { if (!open) { setRejectId(null); setRejectError(null); } }}>
        <DialogContent className="rounded-3xl max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-rose-500" />
              Reject Order
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-[12px] uppercase tracking-wide text-muted-foreground block mb-1.5 font-semibold">
                Reason (optional)
              </label>
              <textarea
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                placeholder="Why are you rejecting this order?"
                className="w-full h-24 rounded-xl bg-accent px-3 py-2.5 text-[13px] outline-none border border-border resize-none"
              />
            </div>
            {rejectError && (
              <p className="text-[13px] text-red-600 dark:text-red-400">{rejectError}</p>
            )}
            <div className="flex gap-2">
              <Button variant="outline" className="flex-1 rounded-xl" onClick={() => setRejectId(null)} disabled={rejecting}>
                Cancel
              </Button>
              <Button
                variant="outline"
                className="flex-1 rounded-xl border-rose-500/30 bg-rose-500/8 text-rose-600 hover:bg-rose-500/15"
                onClick={handleRejectConfirm}
                disabled={rejecting}
              >
                {rejecting ? "Rejecting…" : "Reject Order"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
