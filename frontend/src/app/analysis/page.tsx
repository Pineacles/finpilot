"use client";

import { useEffect, useState } from "react";
import { api, AnalysisResult } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Brain,
  TrendingUp,
  Globe,
  BarChart3,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Info,
} from "lucide-react";

const ANALYSIS_TYPES = [
  { type: "position", label: "Position", icon: TrendingUp },
  { type: "macro", label: "Macro", icon: Globe },
  { type: "sector", label: "Sector", icon: BarChart3 },
];

const RISK_COLORS: Record<string, string> = {
  low: "bg-green-500/10 text-green-500",
  medium: "bg-yellow-500/10 text-yellow-500",
  high: "bg-red-500/10 text-red-500",
};

export default function AnalysisPage() {
  const [analyses, setAnalyses] = useState<AnalysisResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);

  const load = () => {
    api.analysisLatest().then(setAnalyses).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const runAnalysis = async (type: string) => {
    setRunning(type);
    try {
      await api.runAnalysis(type);
      load();
    } catch (e) {
      // Will show error via empty state
    } finally {
      setRunning(null);
    }
  };

  const getAnalysis = (type: string) => analyses.find((a) => a.analysis_type === type);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">AI Analysis</h1>
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          <span className="text-sm text-muted-foreground">Powered by Claude</span>
        </div>
      </div>

      <Tabs defaultValue="position">
        <TabsList>
          {ANALYSIS_TYPES.map(({ type, label, icon: Icon }) => (
            <TabsTrigger key={type} value={type}>
              <Icon className="h-4 w-4 mr-1" />{label}
            </TabsTrigger>
          ))}
        </TabsList>

        {ANALYSIS_TYPES.map(({ type, label }) => {
          const analysis = getAnalysis(type);
          const content = analysis?.content;

          return (
            <TabsContent key={type} value={type} className="space-y-4 mt-4">
              <div className="flex justify-between items-center">
                <div>
                  {analysis && (
                    <p className="text-xs text-muted-foreground">
                      Last run: {new Date(analysis.created_at).toLocaleString()} · {analysis.model_used}
                    </p>
                  )}
                </div>
                <Button onClick={() => runAnalysis(type)} disabled={running === type} variant="outline">
                  <RefreshCw className={`h-4 w-4 mr-2 ${running === type ? "animate-spin" : ""}`} />
                  {running === type ? "Analyzing..." : `Run ${label} Analysis`}
                </Button>
              </div>

              {!analysis ? (
                <Card>
                  <CardContent className="py-16 text-center">
                    <Brain className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                    <p className="text-muted-foreground">No {label.toLowerCase()} analysis yet.</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Click &quot;Run {label} Analysis&quot; to generate AI insights for your portfolio.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <>
                  {/* Summary + Risk */}
                  <div className="grid gap-4 md:grid-cols-3">
                    <Card className="md:col-span-2">
                      <CardHeader><CardTitle className="text-base">Summary</CardTitle></CardHeader>
                      <CardContent>
                        <p className="text-sm">{content?.summary || "No summary available."}</p>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader><CardTitle className="text-base">Risk Level</CardTitle></CardHeader>
                      <CardContent className="flex items-center gap-3">
                        {content?.risk_level === "high" && <AlertTriangle className="h-8 w-8 text-red-500" />}
                        {content?.risk_level === "medium" && <Info className="h-8 w-8 text-yellow-500" />}
                        {content?.risk_level === "low" && <CheckCircle2 className="h-8 w-8 text-green-500" />}
                        <Badge className={RISK_COLORS[content?.risk_level || "medium"] || ""}>
                          {content?.risk_level?.toUpperCase() || "UNKNOWN"}
                        </Badge>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Key Insights */}
                  {content?.key_insights && content.key_insights.length > 0 && (
                    <Card>
                      <CardHeader><CardTitle className="text-base">Key Insights</CardTitle></CardHeader>
                      <CardContent>
                        <ul className="space-y-2">
                          {content.key_insights.map((insight, i) => (
                            <li key={i} className="flex gap-2 text-sm">
                              <span className="text-primary mt-0.5">•</span>
                              {insight}
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}

                  {/* Recommendations */}
                  {content?.recommendations && content.recommendations.length > 0 && (
                    <Card>
                      <CardHeader><CardTitle className="text-base">Recommendations</CardTitle></CardHeader>
                      <CardContent>
                        <ul className="space-y-2">
                          {content.recommendations.map((rec, i) => (
                            <li key={i} className="flex gap-2 text-sm">
                              <span className="text-green-500 mt-0.5">→</span>
                              {rec}
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}

                  {/* Position Notes */}
                  {content?.position_notes && Object.keys(content.position_notes).length > 0 && (
                    <Card>
                      <CardHeader><CardTitle className="text-base">Position Notes</CardTitle></CardHeader>
                      <CardContent className="space-y-3">
                        {Object.entries(content.position_notes).map(([symbol, note]) => (
                          <div key={symbol} className="flex gap-3 items-start">
                            <Badge variant="secondary" className="font-mono shrink-0">{symbol}</Badge>
                            <p className="text-sm">{note}</p>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}

                  {/* Macro Outlook */}
                  {content?.macro_outlook && (
                    <Card>
                      <CardHeader><CardTitle className="text-base">Macro Outlook</CardTitle></CardHeader>
                      <CardContent><p className="text-sm">{content.macro_outlook}</p></CardContent>
                    </Card>
                  )}
                </>
              )}
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  );
}
