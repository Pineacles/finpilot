"use client";

import { useEffect, useState } from "react";
import { api, SyncStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Save,
  Brain,
  Bot,
  Mail,
} from "lucide-react";

const LABELS: Record<string, string> = {
  anthropic_api_key: "Anthropic API Key",
  analysis_model: "Analysis Model",
  analysis_endpoint: "Custom Agent Endpoint",
  analysis_auth_header: "Agent Auth Header",
  agent_endpoint: "Agent API Endpoint",
  agent_auth_header: "Agent Auth Header",
  gmail_address: "Gmail Address",
  gmail_app_password: "App Password",
  gmail_poll_interval: "Auto-poll Interval (minutes)",
  gmail_sender_filter: "Sender Emails to Monitor",
};

const PLACEHOLDERS: Record<string, string> = {
  anthropic_api_key: "sk-ant-...",
  analysis_model: "claude-sonnet-4-20250514",
  analysis_endpoint: "https://your-agent.example.com/analyze",
  analysis_auth_header: "Bearer sk-your-token",
  agent_endpoint: "https://your-agent.example.com/api/finpilot",
  agent_auth_header: "Bearer sk-your-token",
  gmail_address: "your-email@gmail.com",
  gmail_app_password: "16-char app password from Google",
  gmail_poll_interval: "e.g. 15 (minutes), 0 = manual only",
  gmail_sender_filter: "e.g. noreply@valiant.ch,alerts@bank.com",
};

const HINTS: Record<string, string> = {
  analysis_endpoint: "If set, analysis requests go to this URL instead of Anthropic.",
  analysis_auth_header: "Sent as Authorization header to your custom endpoint.",
  analysis_model: "Default: claude-sonnet-4-20250514. Change to any Anthropic model ID.",
  agent_endpoint: "Your NanoClaw agent API. Can scrape banks, fetch portfolio data, run scheduled tasks.",
  agent_auth_header: "Auth header for the agent endpoint.",
  gmail_sender_filter: "Default: noreply@valiant.ch. Add more senders comma-separated.",
  gmail_poll_interval: "Set to 15 for every 15 min. 0 or empty = manual only.",
};

const SENSITIVE_KEYS = new Set(["anthropic_api_key", "analysis_auth_header", "agent_auth_header", "gmail_app_password"]);

const GROUP_ICONS: Record<string, typeof Brain> = {
  analysis: Brain,
  agent: Bot,
  gmail: Mail,
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [groups, setGroups] = useState<Record<string, { label: string; keys: string[] }>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [syncStatus, setSyncStatus] = useState<SyncStatus[]>([]);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then((data) => {
      setSettings(data.settings);
      setGroups(data.groups);
    });
    api.syncStatus().then(setSyncStatus);
  }, []);

  const handleChange = (key: string, value: string) => {
    setEdits({ ...edits, [key]: value });
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateSettings(edits);
      // Refresh settings to get masked values
      const data = await api.getSettings();
      setSettings(data.settings);
      setEdits({});
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const [gmailResult, setGmailResult] = useState<string | null>(null);

  const handleSync = async (source: "gmail") => {
    setSyncing(source);
    setGmailResult(null);
    // Auto-save any pending edits before syncing
    if (Object.keys(edits).length > 0) {
      await api.updateSettings(edits);
      const data = await api.getSettings();
      setSettings(data.settings);
      setEdits({});
    }
    try {
      if (source === "gmail") {
        const result = await api.syncGmail();
        setGmailResult(
          result.balance !== null
            ? `${result.new_transactions} new transactions. Balance: CHF ${result.balance.toLocaleString("de-CH", { minimumFractionDigits: 2 })}`
            : `${result.new_transactions} new transactions.${result.errors.length ? " Errors: " + result.errors.join(", ") : ""}`
        );
      }
      setSyncStatus(await api.syncStatus());
    } catch {
      setSyncStatus(await api.syncStatus());
    } finally {
      setSyncing(null);
    }
  };

  const statusIcon = (status: string) => {
    if (status === "success") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    if (status === "failed") return <XCircle className="h-4 w-4 text-red-500" />;
    return <Clock className="h-4 w-4 text-muted-foreground" />;
  };

  const hasEdits = Object.keys(edits).length > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Settings</h1>
        {hasEdits && (
          <Button onClick={handleSave} disabled={saving}>
            <Save className="h-4 w-4 mr-2" />
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        )}
        {saved && (
          <Badge variant="secondary" className="text-green-500">
            <CheckCircle2 className="h-3 w-3 mr-1" /> Saved
          </Badge>
        )}
      </div>

      {/* Settings Groups */}
      {Object.entries(groups).map(([groupKey, group]) => {
        const Icon = GROUP_ICONS[groupKey] || Brain;
        return (
          <Card key={groupKey}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Icon className="h-5 w-5 text-primary" />
                <CardTitle>{group.label}</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {group.keys.map((key) => {
                const currentValue = edits[key] ?? "";
                const savedValue = settings[key] || "";
                const isEdited = key in edits;
                const isSensitive = SENSITIVE_KEYS.has(key);

                return (
                  <div key={key}>
                    <Label className="text-sm">{LABELS[key] || key}</Label>
                    <Input
                      type={isSensitive && !isEdited ? "password" : "text"}
                      placeholder={PLACEHOLDERS[key] || ""}
                      value={isEdited ? currentValue : savedValue}
                      onChange={(e) => handleChange(key, e.target.value)}
                      className="mt-1 font-mono text-sm"
                    />
                    {HINTS[key] && (
                      <p className="text-xs text-muted-foreground mt-1">{HINTS[key]}</p>
                    )}
                  </div>
                );
              })}

              {/* Sync button for gmail */}
              {groupKey === "gmail" && (
                <>
                  <Separator />
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {statusIcon(syncStatus.find((s) => s.source === groupKey)?.status || "never")}
                      <span className="text-sm text-muted-foreground">
                        {syncStatus.find((s) => s.source === groupKey)?.synced_at
                          ? `Last sync: ${new Date(syncStatus.find((s) => s.source === groupKey)!.synced_at!).toLocaleString()}`
                          : "Never synced"}
                      </span>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleSync("gmail")}
                      disabled={syncing === groupKey}
                    >
                      <RefreshCw className={`h-4 w-4 mr-2 ${syncing === groupKey ? "animate-spin" : ""}`} />
                      Poll Emails
                    </Button>
                  </div>
                  {groupKey === "gmail" && gmailResult && (
                    <p className="text-xs text-green-500 mt-2">{gmailResult}</p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        );
      })}

      {/* Profile */}
      <Card>
        <CardHeader><CardTitle>Profile</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            <p><span className="text-muted-foreground">Email:</span> user@example.com</p>
            <p><span className="text-muted-foreground">Currency:</span> CHF</p>
            <p><span className="text-muted-foreground">App:</span> FinPilot v0.1.0</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
