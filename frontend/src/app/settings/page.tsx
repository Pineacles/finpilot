"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Save, CheckCircle2, RefreshCw, Brain, Bot, Mail, Clock, XCircle } from "lucide-react";

function GlassCard({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay, ease: [0.25, 0.46, 0.45, 0.94] }} className={`glass bg-card rounded-3xl p-6 ${className}`}>
      {children}
    </motion.div>
  );
}

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

  useEffect(() => {
    Promise.all([api.getSettings(), api.syncStatus()]).then(([s, st]) => {
      setSettings(s.settings); setGroups(s.groups); setSyncStatus(st);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try { await api.updateSettings(edits); const d = await api.getSettings(); setSettings(d.settings); setEdits({}); setSaved(true); setTimeout(() => setSaved(false), 3000); }
    finally { setSaving(false); }
  };

  const handleSync = async (source: "gmail") => {
    setSyncing(source); setGmailResult(null);
    if (Object.keys(edits).length > 0) { await api.updateSettings(edits); const d = await api.getSettings(); setSettings(d.settings); setEdits({}); }
    try {
      const r = await api.syncGmail();
      setGmailResult(r.balance !== null ? `${r.new_transactions} new. Balance: CHF ${r.balance.toLocaleString("de-CH", { minimumFractionDigits: 2 })}` : `${r.new_transactions} new.${r.errors.length ? " " + r.errors.join(", ") : ""}`);
      setSyncStatus(await api.syncStatus());
    } catch { setSyncStatus(await api.syncStatus()); }
    finally { setSyncing(null); }
  };

  const handleChange = (key: string, value: string) => { setEdits({ ...edits, [key]: value }); };
  const hasEdits = Object.keys(edits).length > 0;

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center justify-between">
        <div><p className="text-sm font-medium text-primary mb-1">Settings</p><h1 className="text-3xl font-bold tracking-tight">Configuration</h1></div>
        <div className="flex items-center gap-3">
          {saved && <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 rounded-xl"><CheckCircle2 className="h-3 w-3 mr-1" />Saved</Badge>}
          {hasEdits && <Button onClick={handleSave} disabled={saving} className="rounded-xl"><Save className="h-4 w-4 mr-1.5" />{saving ? "Saving..." : "Save Changes"}</Button>}
        </div>
      </motion.div>

      {Object.entries(groups).map(([groupKey, group], gi) => {
        const Icon = GROUP_ICONS[groupKey] || Brain;
        const status = syncStatus.find((s: any) => s.source === groupKey);
        return (
          <GlassCard key={groupKey} delay={0.05 + gi * 0.05}>
            <div className="flex items-center gap-3 mb-5">
              <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
                <Icon className="h-5 w-5 text-muted-foreground" />
              </div>
              <h2 className="text-lg font-semibold">{group.label}</h2>
            </div>

            <div className="space-y-4">
              {group.keys.map(key => {
                const current = edits[key] ?? settings[key] ?? "";
                const isSensitive = SENSITIVE.has(key);
                return (
                  <div key={key}>
                    <label className="text-[13px] text-muted-foreground block mb-1.5">{LABELS[key] || key}</label>
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
                    {status?.status === "success" ? <CheckCircle2 className="h-4 w-4 text-gain" /> : status?.status === "failed" ? <XCircle className="h-4 w-4 text-loss" /> : <Clock className="h-4 w-4" />}
                    {status?.synced_at ? `Last: ${new Date(status.synced_at).toLocaleString()}` : "Never synced"}
                  </div>
                  <Button variant="outline" onClick={() => handleSync("gmail")} disabled={syncing === "gmail"} className="rounded-xl">
                    <RefreshCw className={`h-4 w-4 mr-1.5 ${syncing === "gmail" ? "animate-spin" : ""}`} />
                    Poll Emails
                  </Button>
                </div>
                {gmailResult && <p className="text-[13px] text-gain mt-2">{gmailResult}</p>}
              </div>
            )}
          </GlassCard>
        );
      })}
    </div>
  );
}
