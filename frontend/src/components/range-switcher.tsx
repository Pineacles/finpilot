"use client";

interface RangeSwitcherProps {
  ranges: string[];
  active: string;
  onChange: (r: string) => void;
  className?: string;
}

export function RangeSwitcher({ ranges, active, onChange, className = "" }: RangeSwitcherProps) {
  return (
    <div className={`flex items-center gap-1 p-1 glass bg-card rounded-[14px] ${className}`}>
      {ranges.map((r) => (
        <button
          key={r}
          onClick={() => onChange(r)}
          className={`px-3 py-1.5 rounded-[10px] text-[12px] font-semibold transition-all duration-150 cursor-pointer ${
            r === active
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-accent"
          }`}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
