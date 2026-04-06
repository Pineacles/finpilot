"use client";

import { useEffect, useState } from "react";
import { api, SyncStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RefreshCw, CheckCircle2, XCircle, Clock } from "lucide-react";

export default function SettingsPage() {
  const [syncStatus, setSyncStatus] = useState<SyncStatus[]>([]);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [visecaCookie, setVisecaCookie] = useState("");
  const [visecaCardId, setVisecaCardId] = useState("");

  useEffect(() => {
    api.syncStatus().then(setSyncStatus);
  }, []);

  const handleSync = async (source: "saxo" | "viseca") => {
    setSyncing(source);
    try {
      if (source === "saxo") await api.syncSaxo();
      else await api.syncViseca();
      const status = await api.syncStatus();
      setSyncStatus(status);
    } catch (e) {
      // Error handled by sync status
    } finally {
      setSyncing(null);
    }
  };

  const statusIcon = (status: string) => {
    if (status === "success") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    if (status === "failed") return <XCircle className="h-4 w-4 text-red-500" />;
    return <Clock className="h-4 w-4 text-muted-foreground" />;
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Settings</h1>

      {/* Sync Status */}
      <Card>
        <CardHeader><CardTitle>Data Connections</CardTitle></CardHeader>
        <CardContent className="space-y-6">
          {/* Saxo Bank */}
          <div className="flex items-center justify-between p-4 rounded-lg border">
            <div className="flex items-center gap-3">
              {statusIcon(syncStatus.find((s) => s.source === "saxo")?.status || "never")}
              <div>
                <p className="font-medium">Saxo Bank</p>
                <p className="text-xs text-muted-foreground">
                  {syncStatus.find((s) => s.source === "saxo")?.synced_at
                    ? `Last sync: ${new Date(syncStatus.find((s) => s.source === "saxo")!.synced_at!).toLocaleString()}`
                    : "Never synced"}
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => handleSync("saxo")} disabled={syncing === "saxo"}>
              <RefreshCw className={`h-4 w-4 mr-2 ${syncing === "saxo" ? "animate-spin" : ""}`} />
              Sync
            </Button>
          </div>

          {/* Viseca One */}
          <div className="space-y-4 p-4 rounded-lg border">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {statusIcon(syncStatus.find((s) => s.source === "viseca")?.status || "never")}
                <div>
                  <p className="font-medium">Viseca One</p>
                  <p className="text-xs text-muted-foreground">
                    {syncStatus.find((s) => s.source === "viseca")?.synced_at
                      ? `Last sync: ${new Date(syncStatus.find((s) => s.source === "viseca")!.synced_at!).toLocaleString()}`
                      : "Never synced"}
                  </p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => handleSync("viseca")} disabled={syncing === "viseca"}>
                <RefreshCw className={`h-4 w-4 mr-2 ${syncing === "viseca" ? "animate-spin" : ""}`} />
                Sync
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <Label className="text-xs">Session Cookie (AL_SESS-S)</Label>
                <Input
                  placeholder="Paste cookie value..."
                  value={visecaCookie}
                  onChange={(e) => setVisecaCookie(e.target.value)}
                  className="text-xs"
                />
              </div>
              <div>
                <Label className="text-xs">Card ID</Label>
                <Input
                  placeholder="Card ID from Viseca"
                  value={visecaCardId}
                  onChange={(e) => setVisecaCardId(e.target.value)}
                  className="text-xs"
                />
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              disabled={!visecaCookie || !visecaCardId}
              onClick={async () => {
                await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/sync/viseca/session?cookie=${encodeURIComponent(visecaCookie)}&card_id=${encodeURIComponent(visecaCardId)}`, {
                  method: "POST",
                  headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
                });
              }}
            >
              Save Session
            </Button>
          </div>
        </CardContent>
      </Card>

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
