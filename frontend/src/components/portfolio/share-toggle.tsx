"use client";

import { useEffect, useState } from "react";
import { Globe, Link2, ClipboardCheck } from "lucide-react";
import { api } from "@/lib/api";

// Public-share on/off switch + copy-link button for the portfolio page header.
export function ShareToggle() {
  const [enabled, setEnabled] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.publicPortfolioStatus().then((s) => { setEnabled(s.enabled); setToken(s.token); }).catch(() => {});
  }, []);

  const toggle = async () => {
    setToggling(true);
    try {
      const r = await api.publicPortfolioToggle();
      setEnabled(r.enabled);
      setToken(r.token);
      setCopied(false);
    } finally {
      setToggling(false);
    }
  };

  return (
    <div className="flex items-center gap-2 mr-2">
      <button
        disabled={toggling}
        onClick={toggle}
        className={`relative h-7 w-12 rounded-full transition-colors cursor-pointer ${enabled ? "bg-primary" : "bg-muted"}`}
      >
        <span className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-5" : "translate-x-0"}`} />
      </button>
      <Globe className={`h-4 w-4 ${enabled ? "text-primary" : "text-muted-foreground"}`} />
      {enabled && token && (
        <button
          onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/p/${token}`); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          className="h-8 px-3 rounded-xl bg-accent text-[13px] font-medium flex items-center gap-1.5 hover:bg-muted transition-colors cursor-pointer font-sans"
        >
          {copied ? <><ClipboardCheck className="h-3.5 w-3.5 text-gain" />Copied</> : <><Link2 className="h-3.5 w-3.5" />Copy link</>}
        </button>
      )}
    </div>
  );
}
