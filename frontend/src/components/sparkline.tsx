interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  filled?: boolean;
  stroke?: number;
}

export function Sparkline({ data, width = 80, height = 24, color, filled = false, stroke = 2 }: SparklineProps) {
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`)
    .join(" ");

  const lineColor = color ?? "var(--primary)";

  if (filled) {
    const first = `${0},${height}`;
    const last = `${width},${height}`;
    const fillPts = `${first} ${pts} ${last}`;
    return (
      <svg width={width} height={height} style={{ display: "block" }}>
        <polygon
          fill={lineColor}
          fillOpacity={0.15}
          stroke="none"
          points={fillPts}
        />
        <polyline
          fill="none"
          stroke={lineColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
          points={pts}
        />
      </svg>
    );
  }

  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline
        fill="none"
        stroke={lineColor}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={pts}
      />
    </svg>
  );
}
