"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import {
  LayoutDashboard,
  TrendingUp,
  ArrowLeftRight,
  BarChart3,
  Tag,
  Settings,
  LogOut,
  Sun,
  Moon,
  PiggyBank,
  Target,
  Store,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

const nav = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: TrendingUp },
  { href: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { href: "/stats", label: "Statistics", icon: BarChart3 },
  { href: "/budgets", label: "Budgets", icon: PiggyBank },
  { href: "/goals", label: "Goals", icon: Target },
  { href: "/categories", label: "Categories", icon: Tag },
  { href: "/merchants", label: "Rules", icon: Store },
  { href: "/settings", label: "Settings", icon: Settings },
];

// Theme preference lives in localStorage/matchMedia, outside React. Reading
// it via useSyncExternalStore (rather than useState + an effect that calls
// setState synchronously — react-hooks/set-state-in-effect) renders the
// server-safe default on first paint and swaps in the real value once the
// client can check localStorage, without a hydration-mismatch warning.
type ThemeListener = () => void;
let themeListeners: ThemeListener[] = [];

function notifyThemeChange() {
  themeListeners.forEach((listener) => listener());
}

function subscribeTheme(callback: ThemeListener) {
  themeListeners.push(callback);
  window.addEventListener("storage", callback);
  return () => {
    themeListeners = themeListeners.filter((l) => l !== callback);
    window.removeEventListener("storage", callback);
  };
}

function getThemeSnapshot() {
  const stored = localStorage.getItem("theme");
  return stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

function getThemeServerSnapshot() {
  return false;
}

export function Sidebar() {
  const pathname = usePathname();
  const { logout } = useAuth();
  const dark = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getThemeServerSnapshot);

  // Synchronize the `dark` class on <html> with the current theme — a
  // genuine external-system side effect, not a setState call, so it belongs
  // in an effect.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const toggleTheme = () => {
    const next = !dark;
    localStorage.setItem("theme", next ? "dark" : "light");
    notifyThemeChange();
  };

  return (
    <aside className="flex h-screen w-[240px] flex-col glass bg-sidebar shrink-0 px-3.5 py-5">
      {/* Brand */}
      <div className="flex items-center gap-3 px-[10px] pb-5">
        <div
          className="h-[38px] w-[38px] rounded-[12px] flex items-center justify-center shrink-0"
          style={{ background: "linear-gradient(135deg, #2f5bff, #8b5cf6)", boxShadow: "0 6px 20px -6px rgba(47,91,255,0.5)" }}
        >
          <TrendingUp className="h-[18px] w-[18px] text-white" strokeWidth={2.4} />
        </div>
        <div>
          <span className="text-[16px] font-bold" style={{ letterSpacing: '-0.2px' }}>Finpilot</span>
          <p className="text-[11px] text-muted-foreground">Agent-first finance</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-0.5 overflow-auto">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-[14px] px-3.5 py-[11px] text-[14px] transition-all duration-200 cursor-pointer active:scale-[0.98] ${
                active
                  ? "bg-primary/10 text-primary font-semibold"
                  : "text-muted-foreground font-medium hover:text-foreground hover:bg-accent"
              }`}
              style={active ? { boxShadow: '0 8px 22px -8px rgba(59,130,246,0.3)' } : {}}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={active ? 2.2 : 1.8} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="flex flex-col gap-0.5 pt-2 border-t border-border">
        <button
          onClick={toggleTheme}
          className="flex w-full items-center gap-3 rounded-[14px] px-3.5 py-[11px] text-[14px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-all duration-200 cursor-pointer active:scale-[0.98]"
        >
          {dark ? <Sun className="h-[18px] w-[18px]" strokeWidth={1.8} /> : <Moon className="h-[18px] w-[18px]" strokeWidth={1.8} />}
          {dark ? "Light Mode" : "Dark Mode"}
        </button>
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-[14px] px-3.5 py-[11px] text-[14px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-all duration-200 cursor-pointer active:scale-[0.98]"
        >
          <LogOut className="h-[18px] w-[18px]" strokeWidth={1.8} />
          Logout
        </button>
      </div>
    </aside>
  );
}
