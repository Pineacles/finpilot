interface LivePillProps {
  className?: string;
}

export function LivePill({ className = "" }: LivePillProps) {
  return (
    <span className={`live-pill ${className}`}>
      <span className="dot" />
      LIVE
    </span>
  );
}
