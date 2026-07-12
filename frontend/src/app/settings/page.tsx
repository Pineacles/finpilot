"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { api, type BrokerList, type BrokerStatus, type SyncStatus, type CreditCardAccount, type AiTestResult } from "@/lib/api";
import { GlassCard } from "@/components/glass-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Save, CheckCircle2, RefreshCw, Brain, Bot, Mail, Clock, XCircle,
  Key, ClipboardCheck, Copy, AlertTriangle, User, Building2, Plug, PlugZap, Link2Off,
  CreditCard, Tag,
} from "lucide-react";

const DEFAULT_SETTLEMENT_PATTERNS = ["cembra", "cumulus", "migros bank cumulus", "viseca payment services", "viseca card services"];

const LABELS: Record<string, string> = {
  agent_endpoint: "Agent API Endpoint", agent_auth_header: "Agent Auth Header",
  gmail_address: "Gmail Address", gmail_app_password: "App Password",
  gmail_poll_interval: "Auto-poll Interval (minutes)", gmail_sender_filter: "Sender Emails to Monitor",
};
const PLACEHOLDERS: Record<string, string> = {
  agent_endpoint: "https://your-agent.example.com/api/finpilot", agent_auth_header: "Bearer sk-your-token",
  gmail_address: "your-email@gmail.com", gmail_app_password: "16-char app password",
  gmail_poll_interval: "15 (minutes), 0 = manual", gmail_sender_filter: "noreply@valiant.ch",
};
const SENSITIVE = new Set(["agent_auth_header", "gmail_app_password"]);
const GROUP_ICONS: Record<string, typeof Brain> = { agent: Bot, gmail: Mail };

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [groups, setGroups] = useState<Record<string, { label: string; keys: string[] }>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [gmailResult, setGmailResult] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [apiKeyCopied, setApiKeyCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [newApiKey, setNewApiKey] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getSettings(), api.syncStatus()]).then(([s, st]) => {
      setSettings(s.settings); setGroups(s.groups); setSyncStatus(st);
      if (s.api_key) setApiKey(s.api_key);
    });
  }, []);

  const handleRegenerateApiKey = async () => {
    if (!confirm("Regenerate your API key? Any agents using the current key will stop working until updated.")) return;
    setRegenerating(true);
    try {
      const r = await api.regenerateApiKey();
      setNewApiKey(r.api_key);
      setApiKey("••••••••••••" + r.api_key.slice(-4));
    } catch {
      alert("Failed to regenerate API key.");
    } finally {
      setRegenerating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateSettings(edits);
      const d = await api.getSettings();
      setSettings(d.settings); setEdits({}); setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally { setSaving(false); }
  };

  const handleSync = async (source: "gmail") => {
    setSyncing(source); setGmailResult(null);
    if (Object.keys(edits).length > 0) {
      await api.updateSettings(edits);
      const d = await api.getSettings();
      setSettings(d.settings); setEdits({});
    }
    try {
      const r = await api.syncGmail();
      setGmailResult(
        r.balance !== null
          ? `${r.new_transactions} new. Balance: CHF ${r.balance.toLocaleString("de-CH", { minimumFractionDigits: 2 })}`
          : `${r.new_transactions} new.${r.errors.length ? " " + r.errors.join(", ") : ""}`
      );
      setSyncStatus(await api.syncStatus());
    } catch { setSyncStatus(await api.syncStatus()); }
    finally { setSyncing(null); }
  };

  const handleChange = (key: string, value: string) => { setEdits({ ...edits, [key]: value }); };
  const hasEdits = Object.keys(edits).length > 0;

  // Flushes any pending (unsaved) edits before an action that needs the
  // latest settings server-side (OAuth connect, AI test connection, ...).
  const flushEdits = async () => {
    if (Object.keys(edits).length > 0) {
      await api.updateSettings(edits);
      const d = await api.getSettings();
      setSettings(d.settings); setEdits({});
    }
  };

  return (
    <div className="space-y-6">
      {/* Action bar */}
      {(saved || hasEdits) && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-end gap-3"
        >
          {saved && (
            <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 rounded-xl">
              <CheckCircle2 className="h-3 w-3 mr-1" />Saved
            </Badge>
          )}
          {hasEdits && (
            <Button onClick={handleSave} disabled={saving} className="rounded-xl">
              <Save className="h-4 w-4 mr-1.5" />{saving ? "Saving..." : "Save Changes"}
            </Button>
          )}
        </motion.div>
      )}

      {/* Profile card */}
      <GlassCard delay={0.02}>
        <div className="flex items-center gap-4">
          <div className="h-14 w-14 rounded-[18px] bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center shrink-0">
            <User className="h-7 w-7 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[16px] font-bold">FinPilot User</p>
            <p className="text-[13px] text-muted-foreground truncate">
              {settings["gmail_address"] || "your-gmail@example.com"} · FinPilot
            </p>
          </div>
          <div className="hidden sm:flex gap-6 text-[12px] shrink-0">
            <div className="text-center">
              <p className="text-muted-foreground mb-1">Currency</p>
              <p className="font-600 font-semibold">CHF</p>
            </div>
            <div className="text-center">
              <p className="text-muted-foreground mb-1">Locale</p>
              <p className="font-semibold">de-CH</p>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* API Key card */}
      {apiKey && (
        <GlassCard delay={0.06}>
          <div className="flex items-center gap-3 mb-4">
            <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
              <Key className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold">API Key</h2>
              <p className="text-[12px] text-muted-foreground">For your AI agent, use as header: X-API-Key</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <code className="flex-1 h-11 rounded-xl bg-accent px-4 text-[13px] font-mono flex items-center overflow-x-auto select-all">
              {apiKey}
            </code>
            <button
              onClick={handleRegenerateApiKey}
              disabled={regenerating}
              className="h-11 px-4 rounded-xl bg-accent hover:bg-muted transition-colors cursor-pointer flex items-center gap-1.5 text-[13px] font-medium shrink-0"
              title="Regenerate API key"
            >
              <RefreshCw className={`h-4 w-4 ${regenerating ? "animate-spin" : ""}`} />
            </button>
          </div>
          {newApiKey && (
            <div className="mt-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30">
              <p className="text-[12px] text-amber-600 dark:text-amber-400 font-semibold mb-1">
                New API key, copy it now, it will not be shown again:
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[12px] font-mono break-all">{newApiKey}</code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(newApiKey);
                    setApiKeyCopied(true);
                    setTimeout(() => setApiKeyCopied(false), 2000);
                  }}
                  className="h-8 px-3 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 transition-colors flex items-center gap-1 text-[12px] shrink-0"
                >
                  {apiKeyCopied
                    ? <><ClipboardCheck className="h-3 w-3 text-emerald-500" />Copied</>
                    : <><Copy className="h-3 w-3" />Copy</>}
                </button>
              </div>
            </div>
          )}
        </GlassCard>
      )}

      {/* AI categorization */}
      <AiSection
        settings={settings}
        edits={edits}
        onChange={handleChange}
        onSaveThenAction={flushEdits}
      />

      {/* Settings groups */}
      {Object.entries(groups).map(([groupKey, group], gi) => {
        const Icon = GROUP_ICONS[groupKey] || Brain;
        const status = syncStatus.find((s) => s.source === groupKey);
        return (
          <GlassCard key={groupKey} delay={0.1 + gi * 0.05}>
            <div className="flex items-center gap-3 mb-5">
              <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
                <Icon className="h-5 w-5 text-muted-foreground" />
              </div>
              <h2 className="text-[16px] font-semibold">{group.label}</h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {group.keys.map(key => {
                const current = edits[key] ?? settings[key] ?? "";
                const isSensitive = SENSITIVE.has(key);
                const isWide = current.length > 30 || key.includes("endpoint") || key.includes("filter");
                return (
                  <div key={key} className={isWide ? "sm:col-span-2" : ""}>
                    <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                      {LABELS[key] || key}
                    </label>
                    <Input
                      type={isSensitive ? "password" : "text"}
                      value={current}
                      onChange={e => handleChange(key, e.target.value)}
                      placeholder={PLACEHOLDERS[key] || ""}
                      className="rounded-xl h-11"
                    />
                  </div>
                );
              })}
            </div>

            {groupKey === "gmail" && (
              <div className="mt-5 pt-5 border-t border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
                    {status?.status === "success"
                      ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      : status?.status === "failed"
                        ? <XCircle className="h-4 w-4 text-red-500" />
                        : <Clock className="h-4 w-4" />}
                    {status?.synced_at
                      ? `Last synced: ${new Date(status.synced_at).toLocaleString()}`
                      : "Never synced"}
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => handleSync("gmail")}
                    disabled={syncing === "gmail"}
                    className="rounded-xl"
                  >
                    <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing === "gmail" ? "animate-spin" : ""}`} />
                    Poll now
                  </Button>
                </div>
                {gmailResult && <p className="text-[13px] text-emerald-500 mt-2">{gmailResult}</p>}
              </div>
            )}
          </GlassCard>
        );
      })}

      {/* Brokers */}
      <Suspense fallback={null}>
        <BrokersSection
          settings={settings}
          edits={edits}
          onChange={handleChange}
          onSaveThenAction={flushEdits}
        />
      </Suspense>

      {/* Accounts: credit-card settlement patterns */}
      <AccountsSection />

      {/* Danger zone */}
      <GlassCard delay={0.32} className="border-l-4 border-l-red-500/70">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle className="h-4 w-4 text-red-500" />
          <h2 className="text-[14px] font-bold text-red-500">Danger zone</h2>
        </div>
        <p className="text-[12px] text-muted-foreground mb-4">These actions cannot be undone.</p>
        <div className="flex gap-3">
          <Button variant="outline" size="sm" className="rounded-xl text-[12px]">
            Export all data
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-xl text-[12px] border-red-500/30 bg-red-500/8 text-red-500 hover:bg-red-500/15"
          >
            Delete account
          </Button>
        </div>
      </GlassCard>
    </div>
  );
}


// ─── Brokers section ────────────────────────────────────────────────────────

const BROKER_STATE_PILL: Record<BrokerStatus["state"], { label: string; cls: string }> = {
  disabled:        { label: "Disabled",          cls: "bg-muted text-muted-foreground" },
  setup_required:  { label: "Setup required",    cls: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400" },
  needs_auth:      { label: "Needs reconnect",   cls: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400" },
  connecting:      { label: "Connecting…",       cls: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400" },
  connected:       { label: "Connected",         cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" },
  error:           { label: "Error",             cls: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400" },
};

interface BrokersSectionProps {
  settings: Record<string, string>;
  edits: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onSaveThenAction: () => Promise<void>;
}

function BrokersSection({ settings, edits, onChange, onSaveThenAction }: BrokersSectionProps) {
  const searchParams = useSearchParams();
  const [meta, setMeta] = useState<BrokerList | null>(null);
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [busy, setBusy] = useState<null | "connect" | "disconnect" | "refresh">(null);
  const [banner, setBanner] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const refreshStatus = async () => {
    try { setStatus(await api.saxoStatus()); }
    catch { /* surfaces via the status pill next refresh */ }
  };

  useEffect(() => { api.brokers().then(setMeta).catch(() => {}); refreshStatus(); }, []);

  useEffect(() => {
    const saxo = searchParams.get("saxo");
    if (saxo === "connected") {
      setBanner({ kind: "ok", text: "Saxo connected." });
      refreshStatus();
    } else if (saxo === "error") {
      const reason = searchParams.get("reason") || "unknown";
      setBanner({ kind: "err", text: `Saxo connection failed: ${reason}` });
      refreshStatus();
    }
  }, [searchParams]);

  const value = (k: string) => edits[k] ?? settings[k] ?? "";
  const enabled = value("saxo_enabled") === "1";
  const env = value("saxo_environment") || "sim";
  const hasCreds = Boolean(value("saxo_app_key")) && Boolean(value("saxo_app_secret")) && Boolean(value("saxo_redirect_url"));

  const handleConnect = async () => {
    setBusy("connect"); setBanner(null);
    try {
      await onSaveThenAction();
      const { authorize_url } = await api.saxoConnect();
      window.location.href = authorize_url;
    } catch (e) {
      setBanner({ kind: "err", text: e instanceof Error ? e.message : "Could not start Saxo OAuth flow." });
    } finally {
      setBusy(null);
    }
  };

  const handleDisconnect = async () => {
    setBusy("disconnect");
    try {
      await api.saxoDisconnect();
      await refreshStatus();
      setBanner({ kind: "ok", text: "Saxo disconnected." });
    } catch (e) {
      setBanner({ kind: "err", text: e instanceof Error ? e.message : "Disconnect failed." });
    } finally {
      setBusy(null);
    }
  };

  const pill = status ? BROKER_STATE_PILL[status.state] : null;
  const envOptions = meta?.saxo_environments ?? [
    { value: "sim",  label: "SIM (Simulation)", enabled: true  },
    { value: "live", label: "LIVE",             enabled: false },
  ];

  return (
    <GlassCard delay={0.26}>
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
          <Building2 className="h-5 w-5 text-muted-foreground" />
        </div>
        <h2 className="text-[16px] font-semibold">Brokers</h2>
      </div>

      {banner && (
        <div className={`mb-4 rounded-xl px-3 py-2 text-[13px] ${banner.kind === "ok"
          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : "bg-red-500/10 text-red-600 dark:text-red-400"}`}>
          {banner.text}
        </div>
      )}

      {/* Saxo card */}
      <div className="rounded-2xl border border-border p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-500 flex items-center justify-center">
              <PlugZap className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-[14px] font-semibold">Saxo Bank</p>
              <p className="text-[12px] text-muted-foreground">SIM-only in this release · read-only</p>
            </div>
          </div>
          {pill && (
            <Badge className={`rounded-xl ${pill.cls}`}>{pill.label}</Badge>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Enable toggle */}
          <div>
            <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
              Enable
            </label>
            <button
              type="button"
              onClick={() => onChange("saxo_enabled", enabled ? "0" : "1")}
              className={`h-11 w-full rounded-xl border border-border px-3 flex items-center justify-between transition-colors ${enabled ? "bg-emerald-500/10" : "bg-accent"}`}
            >
              <span className="text-[13px]">{enabled ? "Enabled" : "Disabled"}</span>
              <span className={`h-5 w-9 rounded-full p-0.5 transition-colors ${enabled ? "bg-emerald-500" : "bg-muted-foreground/30"}`}>
                <span className={`block h-4 w-4 rounded-full bg-white transition-transform ${enabled ? "translate-x-4" : ""}`} />
              </span>
            </button>
          </div>

          {/* Environment */}
          <div>
            <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
              Environment
            </label>
            <select
              value={env}
              onChange={e => onChange("saxo_environment", e.target.value)}
              className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
            >
              {envOptions.map(opt => (
                <option key={opt.value} value={opt.value} disabled={!opt.enabled}>
                  {opt.label}{!opt.enabled ? " (not available)" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Credentials */}
          <div>
            <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
              App Key
            </label>
            <Input
              value={value("saxo_app_key")}
              onChange={e => onChange("saxo_app_key", e.target.value)}
              placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              className="rounded-xl h-11 font-mono"
            />
          </div>
          <div>
            <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
              App Secret
            </label>
            <Input
              type="password"
              value={value("saxo_app_secret")}
              onChange={e => onChange("saxo_app_secret", e.target.value)}
              placeholder="••••••••"
              className="rounded-xl h-11 font-mono"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
              Redirect URL
            </label>
            <Input
              value={value("saxo_redirect_url")}
              onChange={e => onChange("saxo_redirect_url", e.target.value)}
              placeholder="https://your-finpilot-domain.example.com/settings/saxo/callback"
              className="rounded-xl h-11"
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Must match the redirect URL registered with your Saxo developer app.
            </p>
          </div>
        </div>

        <div className="mt-5 pt-5 border-t border-border flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground min-w-0">
            {status?.last_error && status.state !== "connected" ? (
              <span className="text-red-500 truncate">{status.last_error}</span>
            ) : (
              <span>Environment: <span className="font-mono">{env.toUpperCase()}</span></span>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={refreshStatus}
              disabled={busy !== null}
              className="rounded-xl"
            >
              <RefreshCw className={`h-4 w-4 mr-1.5 ${busy === "refresh" ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            {status?.state === "connected" || status?.state === "needs_auth" ? (
              <Button
                variant="outline"
                onClick={handleDisconnect}
                disabled={busy !== null}
                className="rounded-xl"
              >
                <Link2Off className="h-4 w-4 mr-1.5" />
                Disconnect
              </Button>
            ) : null}
            <Button
              onClick={handleConnect}
              disabled={busy !== null || !enabled || !hasCreds}
              className="rounded-xl"
            >
              <Plug className="h-4 w-4 mr-1.5" />
              {busy === "connect" ? "Opening…" : "Connect"}
            </Button>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}


// ─── AI categorization section ─────────────────────────────────────────────
// Bring-your-own-model settings for the AI categorization fallback: keyword
// rules, merchant rules, transaction history and the ML classifier all run
// first; only transactions none of those can place get sent to this model.

interface AiSectionProps {
  settings: Record<string, string>;
  edits: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onSaveThenAction: () => Promise<void>;
}

function AiSection({ settings, edits, onChange, onSaveThenAction }: AiSectionProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AiTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const value = (k: string) => edits[k] ?? settings[k] ?? "";
  const enabled = value("ai_enabled") !== "0";
  const providerRaw = value("ai_provider");
  const provider = providerRaw !== "" ? providerRaw : (settings.ai_endpoint ? "custom" : "anthropic");

  const handleTest = async () => {
    setTesting(true); setTestResult(null); setTestError(null);
    try {
      await onSaveThenAction();
      const r = await api.testAiCategorization();
      setTestResult(r);
      if (!r.ok) setTestError(r.error || "Test failed.");
    } catch (e) {
      setTestError(e instanceof Error ? e.message : "Could not test the AI connection.");
    } finally {
      setTesting(false);
    }
  };

  const fieldsCls = enabled ? "" : "opacity-60 pointer-events-none";

  return (
    <GlassCard delay={0.08}>
      <div className="flex items-center gap-3 mb-5">
        <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
          <Brain className="h-5 w-5 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-[16px] font-semibold">AI categorization</h2>
          <p className="text-[12px] text-muted-foreground">Bring your own model for uncategorized transactions</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Enable toggle: always active, even while the section below is dimmed */}
        <div>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Enable
          </label>
          <button
            type="button"
            onClick={() => onChange("ai_enabled", enabled ? "0" : "1")}
            className={`h-11 w-full rounded-xl border border-border px-3 flex items-center justify-between transition-colors ${enabled ? "bg-emerald-500/10" : "bg-accent"}`}
          >
            <span className="text-[13px]">{enabled ? "Enabled" : "Disabled"}</span>
            <span className={`h-5 w-9 rounded-full p-0.5 transition-colors ${enabled ? "bg-emerald-500" : "bg-muted-foreground/30"}`}>
              <span className={`block h-4 w-4 rounded-full bg-white transition-transform ${enabled ? "translate-x-4" : ""}`} />
            </span>
          </button>
        </div>

        <div className={fieldsCls}>
          <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
            Provider
          </label>
          <select
            value={provider}
            onChange={e => onChange("ai_provider", e.target.value)}
            className="h-11 w-full rounded-xl border border-border bg-accent px-3 text-[13px] outline-none"
          >
            <option value="anthropic">Anthropic API</option>
            <option value="openai">OpenAI-compatible</option>
            <option value="custom">Custom gateway</option>
          </select>
        </div>
      </div>

      <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4 ${fieldsCls}`}>
        {provider === "anthropic" && (
          <>
            <div>
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                API Key
              </label>
              <Input
                type="password"
                value={value("ai_api_key")}
                onChange={e => onChange("ai_api_key", e.target.value)}
                placeholder="sk-ant-..."
                className="rounded-xl h-11 font-mono"
              />
            </div>
            <div>
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                Model
              </label>
              <Input
                value={value("ai_model")}
                onChange={e => onChange("ai_model", e.target.value)}
                placeholder="claude-haiku-4-5-20251001"
                className="rounded-xl h-11"
              />
            </div>
          </>
        )}

        {provider === "openai" && (
          <>
            <div className="sm:col-span-2">
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                Base URL
              </label>
              <Input
                value={value("ai_base_url")}
                onChange={e => onChange("ai_base_url", e.target.value)}
                placeholder="https://api.openai.com/v1 or http://localhost:11434/v1"
                className="rounded-xl h-11"
              />
            </div>
            <div>
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                API Key
              </label>
              <Input
                type="password"
                value={value("ai_api_key")}
                onChange={e => onChange("ai_api_key", e.target.value)}
                placeholder="sk-..."
                className="rounded-xl h-11 font-mono"
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                Some servers, such as Ollama, do not need a key. Leave blank.
              </p>
            </div>
            <div>
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                Model
              </label>
              <Input
                value={value("ai_model")}
                onChange={e => onChange("ai_model", e.target.value)}
                placeholder="gpt-5-mini, llama3.1, ..."
                className="rounded-xl h-11"
              />
            </div>
          </>
        )}

        {provider === "custom" && (
          <>
            <div className="sm:col-span-2">
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                Endpoint URL
              </label>
              <Input
                value={value("ai_endpoint")}
                onChange={e => onChange("ai_endpoint", e.target.value)}
                placeholder="https://your-agent.example.com/analyze"
                className="rounded-xl h-11"
              />
            </div>
            <div>
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                Auth Header
              </label>
              <Input
                type="password"
                value={value("ai_auth_header")}
                onChange={e => onChange("ai_auth_header", e.target.value)}
                placeholder="Bearer sk-your-token"
                className="rounded-xl h-11 font-mono"
              />
            </div>
            <div>
              <label className="text-[12px] font-semibold text-muted-foreground block mb-1.5 uppercase tracking-wide">
                Model
              </label>
              <Input
                value={value("ai_model")}
                onChange={e => onChange("ai_model", e.target.value)}
                placeholder="claude-haiku-4-5-20251001"
                className="rounded-xl h-11"
              />
            </div>
          </>
        )}
      </div>

      <div className={fieldsCls}>
        <p className="text-[12px] text-muted-foreground mt-4">
          Transactions that keyword rules, merchant rules, history and the ML classifier cannot
          categorize are sent to this model in small batches. Only merchant names and amounts are sent.
        </p>

        <div className="mt-5 pt-5 border-t border-border">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-[12px] text-muted-foreground">
              Test the current settings against a few sample merchants.
            </p>
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testing}
              className="rounded-xl"
            >
              <RefreshCw className={`h-4 w-4 mr-1.5 ${testing ? "animate-spin" : ""}`} />
              {testing ? "Testing..." : "Test connection"}
            </Button>
          </div>

          {testResult && testResult.ok && (
            <div className="mt-3 rounded-xl px-3 py-2 text-[13px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <p>
                Connected: {testResult.provider} / {testResult.model} in {testResult.latency_ms} ms
              </p>
              {testResult.results.length > 0 && (
                <div className="mt-1.5 space-y-0.5 font-mono text-[12px] opacity-90">
                  {testResult.results.map((r, i) => (
                    <p key={i}>{r.merchant} -&gt; {r.category} ({Math.round(r.confidence * 100)}%)</p>
                  ))}
                </div>
              )}
            </div>
          )}

          {(testError || (testResult && !testResult.ok)) && (
            <div className="mt-3 rounded-xl px-3 py-2 text-[13px] bg-red-500/10 text-red-600 dark:text-red-400">
              {testError || testResult?.error || "Test failed."}
            </div>
          )}
        </div>
      </div>
    </GlassCard>
  );
}


// ─── Accounts section: credit-card settlement patterns ────────────────────
// Configures the issuer-match keywords services/settlement.py uses to detect
// a credit card's bank-side statement payment (e.g. Migros Cumulus, issued
// by Cembra) and auto-reset that card's balance to 0 on import.

function AccountsSection() {
  const [cards, setCards] = useState<CreditCardAccount[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    try {
      const data = await api.creditCardAccounts();
      setCards(data);
      setDrafts(Object.fromEntries(data.map(c => [c.id, (c.settlement_patterns || []).join(", ")])));
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => { load(); }, []);

  if (!loaded || cards.length === 0) return null;

  const handleSave = async (id: string) => {
    setSaving(id); setSavedId(null);
    const patterns = (drafts[id] || "")
      .split(",")
      .map(p => p.trim())
      .filter(Boolean);
    try {
      const updated = await api.updateSettlementPatterns(id, patterns.length ? patterns : null);
      setCards(prev => prev.map(c => (c.id === id ? updated : c)));
      setDrafts(prev => ({ ...prev, [id]: (updated.settlement_patterns || []).join(", ") }));
      setSavedId(id);
      setTimeout(() => setSavedId(null), 2500);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save settlement patterns.");
    } finally {
      setSaving(null);
    }
  };

  const handleReset = async (id: string) => {
    setSaving(id);
    try {
      const updated = await api.updateSettlementPatterns(id, null);
      setCards(prev => prev.map(c => (c.id === id ? updated : c)));
      setDrafts(prev => ({ ...prev, [id]: "" }));
    } finally {
      setSaving(null);
    }
  };

  return (
    <GlassCard delay={0.3}>
      <div className="flex items-center gap-3 mb-2">
        <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
          <CreditCard className="h-5 w-5 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-[16px] font-semibold">Accounts</h2>
          <p className="text-[12px] text-muted-foreground">Credit-card settlement auto-reset</p>
        </div>
      </div>
      <p className="text-[12px] text-muted-foreground mb-5">
        When a bank import contains the payment to your card issuer, FinPilot categorizes it as a
        Transfer and resets that card&apos;s balance to 0. Configure the keywords used to match the
        issuer (comma-separated); leave blank to use the defaults.
      </p>

      <div className="space-y-4">
        {cards.map(card => (
          <div key={card.id} className="rounded-2xl border border-border p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Tag className="h-4 w-4 text-muted-foreground" />
                <p className="text-[14px] font-semibold">{card.name}</p>
                <Badge variant="secondary" className="rounded-lg text-[11px]">{card.currency}</Badge>
              </div>
              {savedId === card.id && (
                <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 rounded-xl">
                  <CheckCircle2 className="h-3 w-3 mr-1" />Saved
                </Badge>
              )}
            </div>
            <Input
              value={drafts[card.id] ?? ""}
              onChange={e => setDrafts(prev => ({ ...prev, [card.id]: e.target.value }))}
              placeholder={`Default: ${DEFAULT_SETTLEMENT_PATTERNS.join(", ")}`}
              className="rounded-xl h-11 text-[13px]"
            />
            <div className="flex justify-end gap-2 mt-3">
              {card.settlement_patterns && card.settlement_patterns.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-xl text-[12px]"
                  onClick={() => handleReset(card.id)}
                  disabled={saving === card.id}
                >
                  Reset to defaults
                </Button>
              )}
              <Button
                size="sm"
                className="rounded-xl text-[12px]"
                onClick={() => handleSave(card.id)}
                disabled={saving === card.id}
              >
                <Save className="h-3.5 w-3.5 mr-1.5" />
                {saving === card.id ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
