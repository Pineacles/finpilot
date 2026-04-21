"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

function SaxoCallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [message, setMessage] = useState("Connecting to Saxo…");

  useEffect(() => {
    const error = params.get("error");
    const code = params.get("code");
    const state = params.get("state");
    if (error) {
      router.replace(`/settings?saxo=error&reason=${encodeURIComponent(error)}`);
      return;
    }
    if (!code || !state) {
      router.replace("/settings?saxo=error&reason=missing_params");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const result = await api.saxoCompleteOAuth(code, state);
        if (cancelled) return;
        if (result.state === "connected") {
          router.replace("/settings?saxo=connected");
        } else {
          const reason = result.last_error || result.state;
          router.replace(`/settings?saxo=error&reason=${encodeURIComponent(reason)}`);
        }
      } catch (e) {
        if (cancelled) return;
        setMessage("Connection failed — redirecting.");
        router.replace("/settings?saxo=error&reason=callback_failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params, router]);

  return (
    <div className="min-h-[50vh] flex items-center justify-center">
      <p className="text-[14px] text-muted-foreground">{message}</p>
    </div>
  );
}

export default function SaxoCallbackPage() {
  return (
    <Suspense fallback={<div className="min-h-[50vh] flex items-center justify-center"><p className="text-[14px] text-muted-foreground">Connecting to Saxo…</p></div>}>
      <SaxoCallbackInner />
    </Suspense>
  );
}
