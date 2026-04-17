"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api } from "@/lib/api";
import { GlassCard } from "@/components/glass-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Save, CheckCircle2, RefreshCw, Brain, Bot, Mail, Clock, XCircle,
  Key, ClipboardCheck, Copy, AlertTriangle, User,
} from "lucide-react";

const LABELS: Record<string, string> = {
  anthropic_api_key: "Anthropic API Key", analysis_model: "Analysis Model",
  analysis_endpoint: "Custom Agent Endpoint", analysis_auth_header: "Agent Auth Header",
  agent_endpoint: "Agent API Endpoint", agent_auth_header: "Agent Auth Header",
  gmail_address: "Gmail Address", gmail_app_password: "App Password",
  gmail_poll_interval: "Auto-poll Interval (minutes)", gmail_sender_filter: "Sender Emails to Monitor",
};
const PLACEHOLDERS: Record<string, string> = {
  anthropic_api_key: "sk-ant-...", analysis_model: "claude-sonnet-4-20250514",
  analysis_endpoint: "https://your-agent.example.com/analyze", analysis_auth_header: "Bearer sk-your-token",
  agent_endpoint: "https://your-agent.example.com/api/finpilot", agent_auth_header: "Bearer sk-your-token",
  gmail_address: "your-email@gmail.com", gmail_app_password: "16-char app password",
  gmail_poll_interval: "15 (minutes), 0 = manual", gmail_sender_filter: "noreply@valiant.ch",
};
const SENSITIVE = new Set(["anthropic_api_key", "analysis_auth_header", "agent_auth_header", "gmail_app_password"]);
const GROUP_ICONS: Record<string, typeof Brain> = { analysis: Brain, agent: Bot, gmail: Mail };

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [groups, setGroups] = useState<Record<string, { label: string; keys: string[] }>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [gmailResult, setGmailResult] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<any[]>([]);
  const [apiKey, setApiKey] = useState("");
  const [apiKeyCopied, setApiKeyCopied] = useState(false);

  useEffect(() => {
    Promise.all([api.getSettings(), api.syncStatus()]).then(([s, st]) => {
      setSettings(s.settings); setGroups(s.groups); setSyncStatus(st);
      if (s.api_key) setApiKey(s.api_key);
    });
  }, []);

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
            <p className="text-base font-bold">Demo User</p>
            <p className="text-[13px] text-muted-foreground truncate">
              {settings["gmail_address"] || "user@example.com"} · FinPilot
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
              <h2 className="text-base font-semibold">API Key</h2>
              <p className="text-[12px] text-muted-foreground">For your AI agent — use as header: X-API-Key</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <code className="flex-1 h-11 rounded-xl bg-accent px-4 text-[13px] font-mono flex items-center overflow-x-auto select-all">
              {apiKey}
            </code>
            <button
              onClick={() => {
                navigator.clipboard.writeText(apiKey);
                setApiKeyCopied(true);
                setTimeout(() => setApiKeyCopied(false), 2000);
              }}
              className="h-11 px-4 rounded-xl bg-accent hover:bg-muted transition-colors cursor-pointer flex items-center gap-1.5 text-[13px] font-medium shrink-0"
            >
              {apiKeyCopied
                ? <><ClipboardCheck className="h-4 w-4 text-emerald-500" />Copied</>
                : <><Copy className="h-4 w-4" />Copy</>}
            </button>
          </div>
        </GlassCard>
      )}

      {/* Settings groups */}
      {Object.entries(groups).map(([groupKey, group], gi) => {
        const Icon = GROUP_ICONS[groupKey] || Brain;
        const status = syncStatus.find((s: any) => s.source === groupKey);
        return (
          <GlassCard key={groupKey} delay={0.1 + gi * 0.05}>
            <div className="flex items-center gap-3 mb-5">
              <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
                <Icon className="h-5 w-5 text-muted-foreground" />
              </div>
              <h2 className="text-base font-semibold">{group.label}</h2>
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

      {/* Danger zone */}
      <GlassCard delay={0.3} className="border-l-4 border-l-red-500/70">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle className="h-4 w-4 text-red-500" />
          <h2 className="text-base font-bold text-red-500">Danger zone</h2>
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
