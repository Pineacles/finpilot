interface CategoryPillProps {
  name: string;
  color?: string;
  className?: string;
}

export function CategoryPill({ name, color = "#6b7280", className = "" }: CategoryPillProps) {
  // Parse hex color to rgb for opacity
  const hex = color.replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  const bg = `rgba(${r}, ${g}, ${b}, 0.22)`;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-[8px] text-[12px] font-medium ${className}`}
      style={{ background: bg, color }}
    >
      {name}
    </span>
  );
}
