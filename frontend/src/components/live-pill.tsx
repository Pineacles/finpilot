interface LivePillProps {
  className?: string;
  // false = polling is paused (e.g. tab hidden), shown as a dim "PAUSED"
  // pill instead of the pinging green "LIVE" one. Never silently keep
  // showing "LIVE" once we've actually stopped refreshing.
  live?: boolean;
}

export function LivePill({ className = "", live = true }: LivePillProps) {
  if (!live) {
    return (
      <span className={`live-pill paused ${className}`} title="Paused: tab is in the background">
        <span className="dot" />
        PAUSED
      </span>
    );
  }
  return (
    <span className={`live-pill ${className}`}>
      <span className="dot" />
      LIVE
    </span>
  );
}
