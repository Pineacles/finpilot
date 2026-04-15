"use client";
import { useEffect, useRef, useState } from "react";
import {
  createChart,
  BaselineSeries,
  LineSeries,
  createSeriesMarkers,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";
import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { ValueTimelinePoint } from "@/lib/api";
import { formatCurrency } from "@/lib/format";

interface TooltipData {
  x: number;
  y: number;
  date: string;
  value: number;
  cost: number;
  pnl: number;
  dailyChange: number;
  tradeLabels: string | null;
}

interface Props {
  data: {
    date: string;
    value: number;
    cost: number;
    pnl: number;
    dailyChange: number;
    tradeLabels: string | null;
    trades: ValueTimelinePoint["trades"];
  }[];
  lastPnlPositive: boolean;
}

export function PortfolioTimelineChart({ data, lastPnlPositive }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const baselineSeriesRef = useRef<ISeriesApi<"Baseline"> | null>(null);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    // Derive the last cost value as baseline price
    const lastCost = data[data.length - 1]?.cost ?? 0;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "rgba(100,116,139,0.9)",
      },
      grid: {
        vertLines: { color: "rgba(148,163,184,0.08)" },
        horzLines: { color: "rgba(148,163,184,0.08)" },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      autoSize: true,
    });

    chartRef.current = chart;

    // Baseline series (value line with green/red fill above/below cost)
    const baselineSeries = chart.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: lastCost },
      topLineColor: "#22c55e",
      topFillColor1: "rgba(34,197,94,0.28)",
      topFillColor2: "rgba(34,197,94,0.04)",
      bottomLineColor: "#ef4444",
      bottomFillColor1: "rgba(239,68,68,0.04)",
      bottomFillColor2: "rgba(239,68,68,0.28)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    baselineSeriesRef.current = baselineSeries;

    baselineSeries.setData(
      data.map((d) => ({ time: d.date as Time, value: d.value }))
    );

    // Cost basis line (dashed, muted)
    const costSeries = chart.addSeries(LineSeries, {
      color: "rgba(148,163,184,0.6)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    costSeries.setData(
      data.map((d) => ({ time: d.date as Time, value: d.cost }))
    );

    // Markers for trades
    const markers: SeriesMarker<Time>[] = [];
    const tradesByDate: Record<string, typeof data[0]["trades"]> = {};
    for (const pt of data) {
      if (pt.trades && pt.trades.length > 0) {
        tradesByDate[pt.date] = pt.trades;
      }
    }

    for (const [date, trades] of Object.entries(tradesByDate)) {
      if (!trades || trades.length === 0) continue;
      const firstTrade = trades[0];
      const isBuy = firstTrade.type === "buy" || firstTrade.type === "deposit";
      const color =
        firstTrade.symbol === "CASH"
          ? firstTrade.type === "deposit"
            ? "#3b82f6"
            : "#f59e0b"
          : firstTrade.type === "buy"
          ? "#22c55e"
          : "#ef4444";

      const textParts = trades.map((t) => {
        if (t.symbol === "CASH") {
          return t.type === "deposit"
            ? `+${Math.round(t.quantity)}`
            : `-${Math.round(t.quantity)}`;
        }
        return `${t.type === "buy" ? "B" : "S"} ${t.quantity} ${t.symbol}`;
      });

      markers.push({
        time: date as Time,
        position: isBuy ? "belowBar" : "aboveBar",
        color,
        shape: "circle",
        size: 1,
        text: textParts.join(", "),
      });
    }

    if (markers.length > 0) {
      createSeriesMarkers(baselineSeries, markers);
    }

    // Crosshair tooltip
    chart.subscribeCrosshairMove((param) => {
      if (
        !param.point ||
        !param.time ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        setTooltip(null);
        return;
      }

      const dateStr = param.time as string;
      const pt = data.find((d) => d.date === dateStr);
      if (!pt) {
        setTooltip(null);
        return;
      }

      const containerWidth = containerRef.current?.clientWidth ?? 300;
      const containerHeight = containerRef.current?.clientHeight ?? 320;
      // Flip tooltip to left side if near right edge
      const x = param.point.x > containerWidth - 180 ? param.point.x - 180 : param.point.x + 16;
      const y = Math.min(param.point.y, containerHeight - 140);

      setTooltip({
        x,
        y,
        date: dateStr,
        value: pt.value,
        cost: pt.cost,
        pnl: pt.pnl,
        dailyChange: pt.dailyChange,
        tradeLabels: pt.tradeLabels,
      });
    });

    return () => {
      chart.remove();
      chartRef.current = null;
      baselineSeriesRef.current = null;
    };
  }, [data]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 bg-popover border border-border rounded-xl p-3 shadow-lg text-[13px] space-y-1 max-w-[260px]"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <p className="font-medium">
            {new Date(tooltip.date).toLocaleDateString("en-CH", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </p>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Value</span>
            <span className="font-semibold tabular-nums">
              {formatCurrency(tooltip.value)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Cost</span>
            <span className="tabular-nums">{formatCurrency(tooltip.cost)}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">P&L</span>
            <span
              className={`font-semibold tabular-nums ${
                tooltip.pnl >= 0 ? "text-gain" : "text-loss"
              }`}
            >
              {tooltip.pnl >= 0 ? "+" : ""}
              {formatCurrency(tooltip.pnl)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Day</span>
            <span
              className={`font-medium tabular-nums ${
                tooltip.dailyChange >= 0 ? "text-gain" : "text-loss"
              }`}
            >
              {tooltip.dailyChange >= 0 ? "+" : ""}
              {formatCurrency(tooltip.dailyChange)}
            </span>
          </div>
          {tooltip.tradeLabels && (
            <div className="pt-1.5 mt-1.5 border-t border-border space-y-0.5">
              {tooltip.tradeLabels.split("\n").map((line, i) => (
                <p
                  key={i}
                  className={`text-[12px] font-medium ${
                    line.startsWith("+")
                      ? line.includes("Deposit")
                        ? "text-blue-500"
                        : "text-gain"
                      : line.includes("Withdraw")
                      ? "text-amber-500"
                      : "text-loss"
                  }`}
                >
                  {line}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
