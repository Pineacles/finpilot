"use client";

import { useState, useEffect, useRef } from "react";

interface AnimatedNumberProps {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}

function useAnimNum(target: number, dur = 700): number {
  const [v, setV] = useState(target);
  const startRef = useRef(target);
  const timeRef = useRef(0);
  const rafRef = useRef(0);

  useEffect(() => {
    if (target === v) return;
    startRef.current = v;
    timeRef.current = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - timeRef.current) / dur, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setV(startRef.current + (target - startRef.current) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return v;
}

export function AnimatedNumber({ value, format, duration = 700, className = "" }: AnimatedNumberProps) {
  const animated = useAnimNum(value, duration);
  const display = format ? format(animated) : animated.toFixed(2);
  return <span className={`tabular ${className}`}>{display}</span>;
}
