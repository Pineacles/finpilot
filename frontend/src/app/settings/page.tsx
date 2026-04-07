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
  TrendingUp,
  CreditCard,
} from "lucide-react";

const LABELS: Record<string, string> = {
  anthropic_api_key: "Anthropic API Key",
  analysis_model: "Analysis Model",
  analysis_endpoint: "Custom Agent Endpoint",
  analysis_auth_header: "Agent Auth Header",
  saxo_app_key: "App Key",
  saxo_app_secret: "App Secret",
  saxo_account_key: "Account Key",
  saxo_access_token: "Access Token",
  saxo_refresh_token: "Refresh Token",
  saxo_token_url: "Token URL",
  saxo_api_url: "API URL",
  viseca_cookie: "Session Cookie (AL_SESS-S)",
  viseca_card_id: "Card ID",
};

const PLACEHOLDERS: Record<string, string> = {
  anthropic_api_key: "sk-ant-...",
  analysis_model: "claude-sonnet-4-20250514",
  analysis_endpoint: "https://your-agent.example.com/analyze",
  analysis_auth_header: "Bearer sk-your-token",
  saxo_app_key: "From developer.saxobank.com",
  saxo_access_token: "Paste OAuth token here",
  saxo_token_url: "https://live.logonvalidation.net/token",
  saxo_api_url: "https://gateway.saxobank.com/openapi",
  viseca_cookie: "From browser DevTools",
  viseca_card_id: "Your Viseca card ID",
};

const HINTS: Record<string, string> = {
  analysis_endpoint: "If set, analysis requests go to this URL instead of Anthropic. Your agent receives market_data + prompts as JSON.",
  analysis_auth_header: "Sent as the Authorization header to your custom endpoint.",
  analysis_model: "Default: claude-sonnet-4-20250514. Change to any Anthropic model ID.",
  saxo_access_token: "Get a 24h token from developer.saxobank.com or complete OAuth flow.",
};

const SENSITIVE_KEYS = new Set(["anthropic_api_key", "saxo_app_secret", "saxo_access_token", "saxo_refresh_token", "viseca_cookie"]);

const GROUP_ICONS: Record<string, typeof Brain> = {
  analysis: Brain,
  saxo: TrendingUp,
  viseca: CreditCard,
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

  const handleSync = async (source: "saxo" | "viseca") => {
    setSyncing(source);
    try {
      if (source === "saxo") await api.syncSaxo();
      else await api.syncViseca();
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

              {/* Sync button for saxo/viseca */}
              {(groupKey === "saxo" || groupKey === "viseca") && (
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
                      onClick={() => handleSync(groupKey as "saxo" | "viseca")}
                      disabled={syncing === groupKey}
                    >
                      <RefreshCw className={`h-4 w-4 mr-2 ${syncing === groupKey ? "animate-spin" : ""}`} />
                      Sync Now
                    </Button>
                  </div>
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
