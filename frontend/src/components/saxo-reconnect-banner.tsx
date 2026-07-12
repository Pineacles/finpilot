"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { api, type BrokerStatus } from "@/lib/api";

/** Yellow banner that appears when the user's Saxo session has expired
 *  and a background refresh failed permanently. Tells the user to click
 *  Reconnect in Settings. Renders nothing otherwise. */
export function SaxoReconnectBanner() {
  const [status, setStatus] = useState<BrokerStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await api.saxoStatus();
        if (!cancelled) setStatus(s);
      } catch { /* ignore: user likely not auth'd yet */ }
    };
    poll();
    const interval = setInterval(poll, 60_000); // re-check every minute
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  if (!status || status.state !== "needs_auth") return null;

  return (
    <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-300 p-4 flex items-start gap-3">
      <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="text-[14px] font-semibold">Saxo session expired</p>
        <p className="text-[12px] opacity-80 mt-0.5">
          Your Saxo refresh token is no longer valid{status.last_error ? ` (${status.last_error})` : ""}.
          Reconnect to resume live sync, live prices, and AI-placed orders.
        </p>
      </div>
      <Link
        href="/settings"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500 text-white text-[12px] font-medium hover:bg-amber-600 transition-colors"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Reconnect
      </Link>
    </div>
  );
}
