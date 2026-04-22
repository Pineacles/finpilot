"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Save, CheckCircle2 } from "lucide-react";
import { GlassCard } from "@/components/glass-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

const NUMERIC_CAPS: [string, string, string][] = [
  ["trading_order_max_chf",          "Per-order Max (CHF)",        "5000"],
  ["trading_daily_count_max",        "Daily Order Count Max",      "20"],
  ["trading_daily_chf_max",          "Daily CHF Max",              "50000"],
  ["trading_position_size_max_pct",  "Position Size Max (%)",      "5"],
  ["trading_per_symbol_max_pct",     "Per-symbol Max (%)",         "3"],
  ["trading_semi_approval_timeout_s","Semi Approval Timeout (s)",  "1800"],
];

export function AiTradingCard() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api.getSettings();
      setSettings(s.settings);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const val = (k: string) => edits[k] ?? settings[k] ?? "";
  const onChange = (k: string, v: string) => setEdits(prev => ({ ...prev, [k]: v }));

  const dirty = useMemo(() => Object.keys(edits).length > 0, [edits]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateSettings(edits);
      await load();
      setEdits({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const aiEnabled = val("trading_ai_enabled") === "1";
  const mode = val("trading_mode") || "off";

  const allowedRaw = val("trading_allowed_actions") || "place,modify,cancel";
  const allowedSet = new Set(allowedRaw.split(",").map(s => s.trim()).filter(Boolean));
  const toggleAction = (action: string) => {
    const next = new Set(allowedSet);
    if (next.has(action)) next.delete(action); else next.add(action);
    onChange("trading_allowed_actions", Array.from(next).join(","));
  };

  if (loading) {
    return (
      <GlassCard>
        <div className="text-[13px] text-muted-foreground">Loading AI trading settings…</div>
      </GlassCard>
    );
  }

  return (
    <GlassCard delay={0.02}>
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
          <Bot className="h-5 w-5 text-white" />
        </div>
        <div className="flex-1">
          <h2 className="text-[16px] font-semibold">AI Trading</h2>
          <p className="text-[12px] text-muted-foreground">
            Semi: you approve each order. Auto: places directly within caps. Off: blocks everything.
          </p>
        </div>
        {dirty && (
          <Button size="sm" onClick={handleSave} disabled={saving} className="gap-1.5">
            {saved ? <CheckCircle2 className="h-4 w-4" /> : <Save className="h-4 w-4" />}
            {saving ? "Saving…" : saved ? "Saved" : "Save"}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Enable AI Trading
          </label>
          <button
            type="button"
            onClick={() => onChange("trading_ai_enabled", aiEnabled ? "0" : "1")}
            className={`h-11 w-full rounded-xl border border-border px-3 flex items-center justify-between transition-colors ${aiEnabled ? "bg-violet-500/10" : "bg-accent"}`}
          >
            <span className="text-[13px]">{aiEnabled ? "Enabled" : "Disabled"}</span>
            <span className={`h-5 w-9 rounded-full p-0.5 transition-colors ${aiEnabled ? "bg-violet-500" : "bg-muted-foreground/30"}`}>
              <span className={`block h-4 w-4 rounded-full bg-white transition-transform ${aiEnabled ? "translate-x-4" : ""}`} />
            </span>
          </button>
        </div>

        <div>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Mode
          </label>
          <select
            value={mode}
            onChange={e => onChange("trading_mode", e.target.value)}
            className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
          >
            <option value="off">Off — blocks all AI orders</option>
            <option value="semi">Semi — human approval required</option>
            <option value="auto">Auto — places directly within caps</option>
          </select>
        </div>

        <div className="sm:col-span-2">
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Allowed Actions
          </label>
          <div className="flex gap-2">
            {["place", "modify", "cancel"].map(action => (
              <button
                key={action}
                type="button"
                onClick={() => toggleAction(action)}
                className={`flex-1 h-11 rounded-xl border border-border text-[13px] font-medium transition-colors cursor-pointer capitalize ${
                  allowedSet.has(action)
                    ? "bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-500/30"
                    : "bg-accent text-muted-foreground"
                }`}
              >
                {action}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Symbol Whitelist
          </label>
          <textarea
            value={val("trading_symbol_whitelist")}
            onChange={e => onChange("trading_symbol_whitelist", e.target.value.replace(/\n/g, ","))}
            placeholder="AAPL, MSFT, NVDA (empty = allow all)"
            rows={2}
            className="w-full rounded-xl border border-border bg-accent px-3 py-2.5 text-[13px] outline-none resize-none font-mono"
          />
        </div>

        <div>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Symbol Blacklist
          </label>
          <textarea
            value={val("trading_symbol_blacklist")}
            onChange={e => onChange("trading_symbol_blacklist", e.target.value.replace(/\n/g, ","))}
            placeholder="GME, AMC (leave empty)"
            rows={2}
            className="w-full rounded-xl border border-border bg-accent px-3 py-2.5 text-[13px] outline-none resize-none font-mono"
          />
        </div>

        {NUMERIC_CAPS.map(([key, label, placeholder]) => (
          <div key={key}>
            <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
              {label}
            </label>
            <Input
              type="number"
              value={val(key)}
              onChange={e => onChange(key, e.target.value)}
              placeholder={placeholder}
              className="rounded-xl h-11"
            />
          </div>
        ))}

        <div>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Timezone
          </label>
          <Input
            value={val("trading_timezone")}
            onChange={e => onChange("trading_timezone", e.target.value)}
            placeholder="Europe/Zurich"
            className="rounded-xl h-11 font-mono"
          />
          <p className="text-[11px] text-muted-foreground mt-1">
            IANA timezone for daily cap resets (e.g. Europe/Zurich, America/New_York)
          </p>
        </div>
      </div>
    </GlassCard>
  );
}
