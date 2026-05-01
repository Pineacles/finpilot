"use client";
import { useEffect, useState, useCallback } from "react";
import {
  api,
  ToolLeaderboardEntry,
  ToolDrillDown,
  ToolRegimeBreakdown,
  ToolCorrelationMatrix,
  ToolWeightProposal,
} from "@/lib/api";
import { GlassCard } from "@/components/glass-card";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  LineChart,
  Line,
  CartesianGrid,
} from "recharts";
import { Lock, Unlock, ChevronDown, Check, X } from "lucide-react";

type TabId = "leaderboard" | "drill-down" | "regime" | "correlation";

const TABS: { id: TabId; label: string }[] = [
  { id: "leaderboard", label: "Leaderboard" },
  { id: "drill-down", label: "Drill-Down" },
  { id: "regime", label: "Regime Breakdown" },
  { id: "correlation", label: "Correlation Matrix" },
];

const REGIME_COLORS: Record<string, string> = {
  expansionary: "var(--chart-1)",
  inflationary: "var(--chart-2)",
  recessionary: "var(--chart-3)",
  stagflationary: "var(--chart-4)",
};

function icColor(ic: number | null): string {
  if (ic === null) return "text-muted-foreground";
  if (ic > 0.05) return "text-gain";
  if (ic < -0.05) return "text-loss";
  return "text-muted-foreground";
}

function fmtIC(ic: number | null): string {
  if (ic === null) return "—";
  return ic.toFixed(3);
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("en-CH", { day: "numeric", month: "short", year: "numeric" });
}

// ── Leaderboard Tab ─────────────────────────────────────────────────────────

function LeaderboardTab({
  entries,
  onDrillDown,
}: {
  entries: ToolLeaderboardEntry[];
  onDrillDown: (name: string) => void;
}) {
  const sorted = [...entries].sort((a, b) => {
    const ai = a.ic_30d ?? -Infinity;
    const bi = b.ic_30d ?? -Infinity;
    return bi - ai;
  });

  if (sorted.length === 0) {
    return (
      <GlassCard>
        <p className="text-[14px] text-muted-foreground text-center py-10">
          No signal data yet. Run a portfolio analysis to start accumulating data.
        </p>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="overflow-hidden p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border">
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Tool</th>
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">IC 30d</th>
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">IC 60d</th>
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Weight</th>
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Locked</th>
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Obs</th>
              <th className="px-5 py-3.5 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Last Changed</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((e, i) => (
              <tr
                key={e.tool_name}
                className="border-b border-border/50 last:border-0 hover:bg-accent/40 transition-colors cursor-pointer"
                onClick={() => onDrillDown(e.tool_name)}
              >
                <td className="px-5 py-3 text-[13px] font-medium">{e.tool_name}</td>
                <td className={`px-5 py-3 text-[13px] font-mono tabular-nums font-semibold ${icColor(e.ic_30d)}`}>
                  {fmtIC(e.ic_30d)}
                </td>
                <td className={`px-5 py-3 text-[13px] font-mono tabular-nums ${icColor(e.ic_60d)}`}>
                  {fmtIC(e.ic_60d)}
                </td>
                <td className="px-5 py-3 text-[13px] font-mono tabular-nums">
                  {e.weight.toFixed(1)}x
                </td>
                <td className="px-5 py-3 text-[13px]">
                  {e.locked
                    ? <Lock className="h-3.5 w-3.5 text-amber-500" />
                    : <Unlock className="h-3.5 w-3.5 text-muted-foreground/40" />
                  }
                </td>
                <td className="px-5 py-3 text-[13px] font-mono tabular-nums text-muted-foreground">
                  {e.observation_count}
                </td>
                <td className="px-5 py-3 text-[13px] text-muted-foreground">
                  {fmtDate(e.last_weight_change)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}

// ── Drill-Down Tab ───────────────────────────────────────────────────────────

const REGIME_DOT_COLORS: Record<string, string> = {
  expansionary: "#3b82f6",
  inflationary: "#f97316",
  recessionary: "#ef4444",
  stagflationary: "#a855f7",
};

function DrillDownTab({ toolNames }: { toolNames: string[] }) {
  const [selected, setSelected] = useState<string>(toolNames[0] ?? "");
  const [data, setData] = useState<ToolDrillDown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (name: string) => {
    if (!name) return;
    setLoading(true);
    setError(null);
    try {
      const d = await api.toolsDrillDown(name);
      setData(d);
    } catch (e: any) {
      setError(e.message ?? "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected) load(selected);
  }, [selected, load]);

  const scatterData = (data?.recent_signals ?? [])
    .filter(s => s.signal_score !== null && s.alpha_5d !== null)
    .map(s => ({
      x: s.signal_score!,
      y: s.alpha_5d!,
      regime: s.regime ?? "unknown",
    }));

  const recentSignals = (data?.recent_signals ?? []).slice(0, 50);

  return (
    <div className="space-y-5">
      {/* Tool selector */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <select
            value={selected}
            onChange={e => setSelected(e.target.value)}
            className="appearance-none glass bg-card rounded-[12px] px-4 py-2.5 pr-9 text-[13px] font-medium cursor-pointer border border-border focus:outline-none"
          >
            {toolNames.length === 0 && <option value="">No tools available</option>}
            {toolNames.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        </div>
      </div>

      {loading && (
        <GlassCard>
          <p className="text-[14px] text-muted-foreground text-center py-8">Loading…</p>
        </GlassCard>
      )}
      {error && (
        <GlassCard>
          <p className="text-[14px] text-loss text-center py-8">{error}</p>
        </GlassCard>
      )}

      {!loading && !error && data && (
        <>
          {/* Scatter plot */}
          <GlassCard>
            <p className="text-[13px] font-semibold mb-4">Signal Score vs Alpha 5d</p>
            {scatterData.length === 0 ? (
              <p className="text-[13px] text-muted-foreground text-center py-8">No signal data available</p>
            ) : (
              <>
                <div className="flex gap-4 mb-3 flex-wrap">
                  {Object.entries(REGIME_DOT_COLORS).map(([regime, color]) => (
                    <div key={regime} className="flex items-center gap-1.5">
                      <div className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                      <span className="text-[11px] text-muted-foreground capitalize">{regime}</span>
                    </div>
                  ))}
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="x" name="Signal Score" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis dataKey="y" name="Alpha 5d" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ strokeDasharray: "3 3" }}
                      content={({ payload }) => {
                        if (!payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="glass bg-card rounded-[12px] p-3 text-[12px] border border-border shadow-lg">
                            <p className="font-semibold capitalize mb-1">{d.regime}</p>
                            <p>Signal: <span className="font-mono">{d.x?.toFixed(3)}</span></p>
                            <p>Alpha 5d: <span className={`font-mono ${d.y >= 0 ? "text-gain" : "text-loss"}`}>{d.y?.toFixed(3)}</span></p>
                          </div>
                        );
                      }}
                    />
                    <ReferenceLine x={0} stroke="var(--border)" strokeWidth={1.5} />
                    <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.5} />
                    {Object.entries(REGIME_DOT_COLORS).map(([regime, color]) => (
                      <Scatter
                        key={regime}
                        name={regime}
                        data={scatterData.filter(d => d.regime === regime)}
                        fill={color}
                        fillOpacity={0.7}
                        r={4}
                      />
                    ))}
                  </ScatterChart>
                </ResponsiveContainer>
              </>
            )}
          </GlassCard>

          {/* IC Time Series */}
          <GlassCard>
            <p className="text-[13px] font-semibold mb-4">Rolling 30d IC Over Time</p>
            {data.ic_time_series.length === 0 ? (
              <p className="text-[13px] text-muted-foreground text-center py-8">No IC time series data available</p>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data.ic_time_series} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={v => new Date(v).toLocaleDateString("en-CH", { month: "short", day: "numeric" })}
                  />
                  <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={v => v.toFixed(2)} />
                  <Tooltip
                    content={({ payload, label }) => {
                      if (!payload?.length) return null;
                      const ic = payload[0].value as number;
                      return (
                        <div className="glass bg-card rounded-[12px] p-3 text-[12px] border border-border shadow-lg">
                          <p className="text-muted-foreground mb-1">{fmtDate(label != null ? String(label) : null)}</p>
                          <p>IC: <span className={`font-mono font-semibold ${icColor(ic)}`}>{ic.toFixed(3)}</span></p>
                        </div>
                      );
                    }}
                  />
                  <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.5} />
                  <Line
                    type="monotone"
                    dataKey="ic"
                    stroke="var(--chart-1)"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </GlassCard>

          {/* Recent Signals Table */}
          <GlassCard className="overflow-hidden p-0">
            <div className="px-[22px] py-4 border-b border-border">
              <p className="text-[13px] font-semibold">Recent Signals</p>
            </div>
            {recentSignals.length === 0 ? (
              <p className="text-[13px] text-muted-foreground text-center py-8 px-[22px]">No signals recorded yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="px-5 py-3 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Date</th>
                      <th className="px-5 py-3 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Symbol</th>
                      <th className="px-5 py-3 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Signal Score</th>
                      <th className="px-5 py-3 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Fwd Return 5d</th>
                      <th className="px-5 py-3 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Alpha 5d</th>
                      <th className="px-5 py-3 text-[11px] uppercase tracking-[0.3px] text-muted-foreground font-semibold">Regime</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentSignals.map((s, i) => (
                      <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-accent/40 transition-colors">
                        <td className="px-5 py-2.5 text-[13px] text-muted-foreground">{fmtDate(s.run_timestamp)}</td>
                        <td className="px-5 py-2.5 text-[13px] font-semibold">{s.symbol ?? "—"}</td>
                        <td className="px-5 py-2.5 text-[13px] font-mono tabular-nums">{s.signal_score !== null ? s.signal_score.toFixed(3) : "—"}</td>
                        <td className={`px-5 py-2.5 text-[13px] font-mono tabular-nums ${s.forward_return_5d !== null ? (s.forward_return_5d >= 0 ? "text-gain" : "text-loss") : "text-muted-foreground"}`}>
                          {s.forward_return_5d !== null ? s.forward_return_5d.toFixed(3) : "—"}
                        </td>
                        <td className={`px-5 py-2.5 text-[13px] font-mono tabular-nums font-semibold ${s.alpha_5d !== null ? icColor(s.alpha_5d) : "text-muted-foreground"}`}>
                          {s.alpha_5d !== null ? s.alpha_5d.toFixed(3) : "—"}
                        </td>
                        <td className="px-5 py-2.5 text-[13px] text-muted-foreground capitalize">{s.regime ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassCard>
        </>
      )}
    </div>
  );
}

// ── Regime Breakdown Tab ─────────────────────────────────────────────────────

const REGIME_LABELS: Record<string, string> = {
  expansionary: "Expansionary",
  inflationary: "Inflationary",
  recessionary: "Recessionary",
  stagflationary: "Stagflationary",
};

function RegimeTab({ toolNames }: { toolNames: string[] }) {
  const [selected, setSelected] = useState<string>(toolNames[0] ?? "");
  const [data, setData] = useState<ToolRegimeBreakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (name: string) => {
    if (!name) return;
    setLoading(true);
    setError(null);
    try {
      const d = await api.toolsRegimeBreakdown(name);
      setData(d);
    } catch (e: any) {
      setError(e.message ?? "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected) load(selected);
  }, [selected, load]);

  const regimes = ["expansionary", "inflationary", "recessionary", "stagflationary"];

  return (
    <div className="space-y-5">
      <div className="relative inline-block">
        <select
          value={selected}
          onChange={e => setSelected(e.target.value)}
          className="appearance-none glass bg-card rounded-[12px] px-4 py-2.5 pr-9 text-[13px] font-medium cursor-pointer border border-border focus:outline-none"
        >
          {toolNames.length === 0 && <option value="">No tools available</option>}
          {toolNames.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      </div>

      {loading && (
        <GlassCard>
          <p className="text-[14px] text-muted-foreground text-center py-8">Loading…</p>
        </GlassCard>
      )}
      {error && (
        <GlassCard>
          <p className="text-[14px] text-loss text-center py-8">{error}</p>
        </GlassCard>
      )}

      {!loading && !error && data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {regimes.map(regime => {
            const stat = data[regime];
            const ic = stat?.ic ?? null;
            const n = stat?.n ?? 0;
            const barWidth = ic !== null ? Math.min(Math.abs(ic) * 100, 100) : 0;
            const barColor = ic !== null && ic > 0 ? "#22c55e" : "#ef4444";

            return (
              <GlassCard key={regime}>
                <div className="flex items-center justify-between mb-3">
                  <div className="h-2.5 w-2.5 rounded-full" style={{ background: REGIME_COLORS[regime] ?? "#888" }} />
                  <span className="text-[11px] text-muted-foreground font-semibold uppercase tracking-[0.3px]">{n} obs</span>
                </div>
                <p className="text-[13px] font-semibold mb-2">{REGIME_LABELS[regime] ?? regime}</p>
                <p className={`text-[32px] font-extrabold font-mono tabular-nums leading-none mb-3 ${icColor(ic)}`} style={{ letterSpacing: "-0.8px" }}>
                  {ic !== null ? ic.toFixed(3) : "—"}
                </p>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${barWidth}%`, background: barColor }}
                  />
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Correlation Matrix Tab ───────────────────────────────────────────────────

function correlationToColor(v: number): string {
  // -1 → red, 0 → white (in light) / dark bg, +1 → green
  if (v >= 0) {
    const g = Math.round(v * 80 + 34);
    const r = Math.round(34 + (1 - v) * 80);
    const b = Math.round(34 + (1 - v) * 40);
    return `rgb(${r},${g},${b})`;
  } else {
    const abs = Math.abs(v);
    const r = Math.round(abs * 80 + 34 + 120);
    const g = Math.round(34 + (1 - abs) * 80);
    const b = Math.round(34 + (1 - abs) * 40);
    return `rgb(${Math.min(r, 239)},${g},${b})`;
  }
}

function CorrelationTab() {
  const [data, setData] = useState<ToolCorrelationMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<{ row: number; col: number } | null>(null);

  useEffect(() => {
    api.toolsCorrelationMatrix()
      .then(setData)
      .catch(e => setError(e.message ?? "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <GlassCard>
      <p className="text-[14px] text-muted-foreground text-center py-8">Loading…</p>
    </GlassCard>
  );
  if (error) return (
    <GlassCard>
      <p className="text-[14px] text-loss text-center py-8">{error}</p>
    </GlassCard>
  );
  if (!data || data.tools.length < 2) return (
    <GlassCard>
      <p className="text-[14px] text-muted-foreground text-center py-10">
        Need more data — at least 2 analysis runs required
      </p>
    </GlassCard>
  );

  const { tools, matrix } = data;

  return (
    <GlassCard>
      <p className="text-[13px] font-semibold mb-5">Tool Correlation Matrix</p>
      <div className="overflow-x-auto">
        <div style={{ display: "grid", gridTemplateColumns: `120px repeat(${tools.length}, 1fr)`, gap: 2, minWidth: tools.length * 60 + 120 }}>
          {/* Header row */}
          <div />
          {tools.map(t => (
            <div
              key={t}
              className="text-[10px] font-semibold text-muted-foreground text-center pb-2"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", height: 80, display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              {t}
            </div>
          ))}

          {/* Data rows */}
          {tools.map((rowTool, rowIdx) => (
            <>
              <div key={`row-${rowTool}`} className="text-[11px] font-medium text-muted-foreground flex items-center pr-3 truncate">{rowTool}</div>
              {tools.map((colTool, colIdx) => {
                const v = matrix[rowIdx]?.[colIdx] ?? 0;
                const isHighCorr = Math.abs(v) > 0.8 && rowIdx !== colIdx;
                const isHov = hovered?.row === rowIdx && hovered?.col === colIdx;
                return (
                  <div
                    key={`${rowIdx}-${colIdx}`}
                    className="relative rounded-[6px] flex items-center justify-center cursor-default transition-all duration-150"
                    style={{
                      background: correlationToColor(v),
                      height: 44,
                      boxShadow: isHighCorr ? "0 0 0 2px rgba(59,130,246,0.6), 0 0 10px rgba(59,130,246,0.3)" : undefined,
                      opacity: isHov ? 0.85 : 1,
                    }}
                    onMouseEnter={() => setHovered({ row: rowIdx, col: colIdx })}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <span className="text-[10px] font-mono tabular-nums font-bold" style={{ color: Math.abs(v) > 0.5 ? "#fff" : "#222" }}>
                      {v.toFixed(2)}
                    </span>
                    {isHov && (
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-10 glass bg-card rounded-[10px] px-3 py-2 text-[11px] border border-border shadow-lg whitespace-nowrap pointer-events-none">
                        {rowTool} × {colTool}: <span className="font-mono font-semibold">{v.toFixed(3)}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3 mt-5">
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-6 rounded" style={{ background: correlationToColor(-1) }} />
          <span className="text-[11px] text-muted-foreground">-1</span>
        </div>
        <div className="flex-1 h-2 rounded" style={{ background: "linear-gradient(to right, rgb(239,80,80), rgb(80,114,80), rgb(34,114,34))" }} />
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-6 rounded" style={{ background: correlationToColor(1) }} />
          <span className="text-[11px] text-muted-foreground">+1</span>
        </div>
        <span className="text-[11px] text-muted-foreground ml-2">Blue border = correlation &gt; 0.8</span>
      </div>
    </GlassCard>
  );
}

// ── Pending Proposals ────────────────────────────────────────────────────────

function PendingProposals({ onRefresh }: { onRefresh: () => void }) {
  const [proposals, setProposals] = useState<ToolWeightProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);

  const loadProposals = useCallback(async () => {
    try {
      const d = await api.toolsPendingProposals();
      setProposals(d);
    } catch {
      setProposals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProposals(); }, [loadProposals]);

  const resolve = async (id: string, resolution: "approved" | "rejected") => {
    setResolving(id);
    try {
      await api.resolveProposal(id, resolution);
      await loadProposals();
      onRefresh();
    } catch {
      // silently fail
    } finally {
      setResolving(null);
    }
  };

  if (loading || proposals.length === 0) return null;

  return (
    <GlassCard className="mt-6">
      <div className="flex items-center gap-3 mb-5">
        <p className="text-[15px] font-bold">Pending Weight Proposals</p>
        <span className="px-2.5 py-1 rounded-xl text-[12px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400">
          {proposals.length}
        </span>
      </div>
      <div className="space-y-4">
        {proposals.map(p => (
          <div key={p.id} className="p-4 rounded-[16px] bg-muted/40 border border-border">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2 flex-wrap">
                  <p className="text-[14px] font-semibold">{p.tool_name}</p>
                  <div className="flex items-center gap-2 text-[13px] font-mono tabular-nums">
                    <span className="text-muted-foreground">{p.current_weight.toFixed(1)}x</span>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-semibold text-primary">{p.proposed_weight.toFixed(1)}x</span>
                  </div>
                  {p.ic_30d !== undefined && p.ic_30d !== null && (
                    <span className={`text-[12px] font-mono ${icColor(p.ic_30d)}`}>IC 30d: {p.ic_30d.toFixed(3)}</span>
                  )}
                  {p.observation_count !== undefined && (
                    <span className="text-[12px] text-muted-foreground">{p.observation_count} obs</span>
                  )}
                </div>
                <p className="text-[13px] text-foreground/70 leading-[1.7]">{p.rationale}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => resolve(p.id, "approved")}
                  disabled={resolving === p.id}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-[10px] bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 text-[13px] font-semibold hover:opacity-80 transition-opacity disabled:opacity-50 cursor-pointer"
                >
                  <Check className="h-3.5 w-3.5" />
                  Approve
                </button>
                <button
                  onClick={() => resolve(p.id, "rejected")}
                  disabled={resolving === p.id}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-[10px] bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 text-[13px] font-semibold hover:opacity-80 transition-opacity disabled:opacity-50 cursor-pointer"
                >
                  <X className="h-3.5 w-3.5" />
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function ToolsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("leaderboard");
  const [leaderboard, setLeaderboard] = useState<ToolLeaderboardEntry[]>([]);
  const [leaderboardLoading, setLeaderboardLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadLeaderboard = useCallback(async () => {
    setLeaderboardLoading(true);
    try {
      const d = await api.toolsLeaderboard();
      setLeaderboard(d);
    } catch {
      setLeaderboard([]);
    } finally {
      setLeaderboardLoading(false);
    }
  }, []);

  useEffect(() => { loadLeaderboard(); }, [loadLeaderboard, refreshKey]);

  const toolNames = leaderboard.map(e => e.tool_name);

  const handleDrillDown = (name: string) => {
    setActiveTab("drill-down");
    // The DrillDownTab handles selection via state, so we just switch tab
    // The first tool in the list will be pre-selected by default
  };

  return (
    <div className="space-y-5">
      {/* Tab switcher */}
      <div className="flex items-center gap-1 p-1 glass bg-card rounded-[14px] w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-1.5 rounded-[10px] text-[13px] font-semibold transition-all duration-150 cursor-pointer ${
              activeTab === t.id
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "leaderboard" && (
        leaderboardLoading ? (
          <GlassCard>
            <p className="text-[14px] text-muted-foreground text-center py-8">Loading…</p>
          </GlassCard>
        ) : (
          <LeaderboardTab entries={leaderboard} onDrillDown={handleDrillDown} />
        )
      )}
      {activeTab === "drill-down" && (
        <DrillDownTab toolNames={toolNames} />
      )}
      {activeTab === "regime" && (
        <RegimeTab toolNames={toolNames} />
      )}
      {activeTab === "correlation" && (
        <CorrelationTab />
      )}

      {/* Pending proposals — always visible below tabs */}
      <PendingProposals onRefresh={() => { setRefreshKey(k => k + 1); }} />
    </div>
  );
}
