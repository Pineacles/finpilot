interface ConvictionDotsProps {
  level: number;
  max?: number;
  className?: string;
}

export function ConvictionDots({ level, max = 5, className = "" }: ConvictionDotsProps) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`} title={`Conviction: ${level}/${max}`}>
      {Array.from({ length: max }, (_, i) => (
        <span
          key={i}
          className="inline-block w-2 h-2 rounded-full transition-colors"
          style={{
            background: i < level ? "var(--primary)" : "var(--border)",
            opacity: i < level ? 1 : 0.4,
          }}
        />
      ))}
    </span>
  );
}
